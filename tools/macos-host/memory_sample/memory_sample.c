// Dumps the readable, non-shared virtual memory of a target process to a
// single file, plus an index describing where each region landed in the
// dump. This is the macOS analog of the Windows `read-memory-64-bit.exe
// save-process-sample` tool referenced in
// guide/how-to-collect-samples-for-64-bit-memory-reading-development.md:
// it is meant to be run together with a screenshot of the game window
// (see save_process_sample.sh) so UI state can later be correlated with
// byte offsets while reverse engineering the CPython object layout.
//
// Regions flagged `shared` (dyld shared cache, mapped frameworks) are
// skipped: they are identical scaffolding present in every process on the
// machine, not per-process heap data, and would otherwise dominate the
// dump size for no benefit.
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define CHUNK_SIZE (4 * 1024 * 1024)

int main(int argc, char **argv) {
    if (argc < 3) {
        fprintf(stderr, "usage: %s <pid> <output_dir>\n", argv[0]);
        return 1;
    }
    pid_t pid = atoi(argv[1]);
    const char *out_dir = argv[2];

    task_t task = MACH_PORT_NULL;
    kern_return_t kr = task_for_pid(mach_task_self(), pid, &task);
    if (kr != KERN_SUCCESS) {
        fprintf(stderr, "task_for_pid failed: %s (kr=%d)\n", mach_error_string(kr), kr);
        return 1;
    }

    char memory_path[1024], index_path[1024];
    snprintf(memory_path, sizeof(memory_path), "%s/memory.bin", out_dir);
    snprintf(index_path, sizeof(index_path), "%s/regions.tsv", out_dir);

    FILE *memory_file = fopen(memory_path, "wb");
    if (!memory_file) {
        perror("fopen memory.bin");
        return 1;
    }
    FILE *index_file = fopen(index_path, "w");
    if (!index_file) {
        perror("fopen regions.tsv");
        fclose(memory_file);
        return 1;
    }
    fprintf(index_file, "address_hex\tsize_hex\tprotection\tshared\tstatus\toffset_in_dump\tbytes_written\n");

    unsigned char *buf = malloc(CHUNK_SIZE);
    if (!buf) {
        fprintf(stderr, "malloc failed\n");
        return 1;
    }

    mach_vm_address_t addr = 0;
    uint64_t dump_offset = 0;
    uint64_t regions_total = 0, regions_dumped = 0, regions_skipped_shared = 0, regions_skipped_noread = 0;
    uint64_t bytes_dumped = 0;

    while (1) {
        mach_vm_size_t size = 0;
        vm_region_basic_info_data_64_t info;
        mach_msg_type_number_t info_count = VM_REGION_BASIC_INFO_COUNT_64;
        mach_port_t object_name = MACH_PORT_NULL;

        kr = mach_vm_region(task, &addr, &size, VM_REGION_BASIC_INFO_64,
                             (vm_region_info_t)&info, &info_count, &object_name);
        if (kr != KERN_SUCCESS) break;

        regions_total++;
        const char *status = "ok";
        uint64_t region_offset = dump_offset;
        uint64_t region_bytes_written = 0;

        if (info.shared) {
            status = "skipped_shared";
            regions_skipped_shared++;
        } else if (!(info.protection & VM_PROT_READ)) {
            status = "skipped_noread";
            regions_skipped_noread++;
        } else {
            mach_vm_size_t remaining = size;
            mach_vm_address_t cursor = addr;
            int had_error = 0;
            while (remaining > 0) {
                mach_vm_size_t want = remaining < CHUNK_SIZE ? remaining : CHUNK_SIZE;
                mach_vm_size_t got = 0;
                kern_return_t rkr = mach_vm_read_overwrite(task, cursor, want, (mach_vm_address_t)buf, &got);
                if (rkr != KERN_SUCCESS || got == 0) {
                    had_error = 1;
                    break;
                }
                if (fwrite(buf, 1, got, memory_file) != got) {
                    perror("fwrite memory.bin");
                    return 1;
                }
                region_bytes_written += got;
                cursor += got;
                remaining -= got;
            }
            status = had_error && region_bytes_written == 0 ? "failed" : (had_error ? "partial" : "ok");
            if (region_bytes_written > 0) {
                regions_dumped++;
                dump_offset += region_bytes_written;
                bytes_dumped += region_bytes_written;
            }
        }

        fprintf(index_file, "0x%llx\t0x%llx\t%d\t%d\t%s\t%llu\t%llu\n",
                addr, size, info.protection, info.shared, status,
                region_bytes_written > 0 ? region_offset : 0, region_bytes_written);

        addr += size;
    }

    free(buf);
    fclose(memory_file);
    fclose(index_file);

    fprintf(stderr,
            "pid=%d regions_total=%llu dumped=%llu skipped_shared=%llu skipped_noread=%llu bytes_dumped=%llu\n",
            pid, regions_total, regions_dumped, regions_skipped_shared, regions_skipped_noread, bytes_dumped);

    return 0;
}
