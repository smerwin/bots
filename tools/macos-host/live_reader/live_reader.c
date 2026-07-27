// Persistent live memory reader: task_for_pid once, then serves an
// unbounded stream of small reads over stdin/stdout without ever writing
// a dump file. This is the fast path for repeatedly reading live process
// state (e.g. walking the UI tree every bot-loop tick); memory_sample's
// full-dump approach is for one-off RE sampling, not repeated reads.
//
// Wire protocol, binary, over stdin/stdout:
//   request:  8 bytes address (LE u64) + 8 bytes length (LE u64)
//   response: 8 bytes bytes-read (LE u64, 0 on failure) + that many bytes
// A zero-length address+length pair (all zero bytes) is not special-cased;
// callers simply stop sending requests to end the session (EOF on stdin
// ends the process).
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define MAX_READ_LEN (1 << 20)  // 1 MiB cap per request, plenty for object reads

static int read_full(int fd, void *buf, size_t n) {
    size_t got = 0;
    while (got < n) {
        ssize_t r = read(fd, (char *)buf + got, n - got);
        if (r <= 0) return -1;
        got += (size_t)r;
    }
    return 0;
}

static int write_full(int fd, const void *buf, size_t n) {
    size_t sent = 0;
    while (sent < n) {
        ssize_t w = write(fd, (const char *)buf + sent, n - sent);
        if (w <= 0) return -1;
        sent += (size_t)w;
    }
    return 0;
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: %s <pid>\n", argv[0]);
        return 1;
    }
    pid_t pid = atoi(argv[1]);

    task_t task = MACH_PORT_NULL;
    kern_return_t kr = task_for_pid(mach_task_self(), pid, &task);
    if (kr != KERN_SUCCESS) {
        fprintf(stderr, "task_for_pid failed: %s (kr=%d)\n", mach_error_string(kr), kr);
        return 1;
    }
    fprintf(stderr, "ready\n");
    fflush(stderr);

    static unsigned char buf[MAX_READ_LEN];
    unsigned char req[16];
    while (read_full(0, req, sizeof(req)) == 0) {
        uint64_t addr, len;
        memcpy(&addr, req, 8);
        memcpy(&len, req + 8, 8);
        if (len > MAX_READ_LEN) len = MAX_READ_LEN;

        mach_vm_size_t got = 0;
        kern_return_t rkr = KERN_FAILURE;
        if (len > 0) {
            rkr = mach_vm_read_overwrite(task, (mach_vm_address_t)addr, (mach_vm_size_t)len,
                                          (mach_vm_address_t)buf, &got);
        }
        uint64_t got64 = (rkr == KERN_SUCCESS) ? (uint64_t)got : 0;

        if (write_full(1, &got64, 8) != 0) break;
        if (got64 > 0 && write_full(1, buf, (size_t)got64) != 0) break;
    }
    return 0;
}
