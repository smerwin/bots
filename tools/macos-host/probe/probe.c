// Minimal Mach VM read probe: given a target PID, attempt task_for_pid,
// then walk the target's VM regions and read the first readable page of
// each, printing address/size/protection. Used to confirm task_for_pid +
// mach_vm_read_overwrite work against a hardened, non-dev-signed target
// once SIP's Debugging Restrictions have been disabled.
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <stdio.h>
#include <stdlib.h>

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
    printf("task_for_pid succeeded for pid %d\n", pid);

    mach_vm_address_t addr = 0;
    int regions_shown = 0;
    const int max_regions = 20;

    while (regions_shown < max_regions) {
        mach_vm_size_t size = 0;
        vm_region_basic_info_data_64_t info;
        mach_msg_type_number_t info_count = VM_REGION_BASIC_INFO_COUNT_64;
        mach_port_t object_name = MACH_PORT_NULL;

        kr = mach_vm_region(task, &addr, &size, VM_REGION_BASIC_INFO_64,
                             (vm_region_info_t)&info, &info_count, &object_name);
        if (kr != KERN_SUCCESS) {
            if (regions_shown == 0) {
                fprintf(stderr, "mach_vm_region failed: %s (kr=%d)\n", mach_error_string(kr), kr);
            }
            break;
        }

        printf("region addr=0x%llx size=0x%llx prot=%d\n", addr, size, info.protection);

        if (info.protection & VM_PROT_READ) {
            unsigned char buf[64];
            mach_vm_size_t out_size = 0;
            kern_return_t rkr = mach_vm_read_overwrite(task, addr, sizeof(buf),
                                                        (mach_vm_address_t)buf, &out_size);
            if (rkr == KERN_SUCCESS) {
                printf("  read %llu bytes ok, first bytes:", out_size);
                for (mach_vm_size_t i = 0; i < out_size && i < 16; i++) {
                    printf(" %02x", buf[i]);
                }
                printf("\n");
            } else {
                printf("  mach_vm_read_overwrite failed: %s (kr=%d)\n", mach_error_string(rkr), rkr);
            }
        }

        addr += size;
        regions_shown++;
    }

    return 0;
}
