/* Linux validation helper: exec a command with IPv4/IPv6 socket creation denied.
 * The seccomp filter is inherited across exec/fork, unlike an LD_PRELOAD hook.
 * AF_UNIX remains available for process IPC and local cache coordination.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <linux/audit.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <unistd.h>

#if defined(__x86_64__)
#define HOST_ARCH AUDIT_ARCH_X86_64
#elif defined(__aarch64__)
#define HOST_ARCH AUDIT_ARCH_AARCH64
#else
#error Unsupported seccomp validation architecture
#endif

static int disable_network(void) {
    struct sock_filter rules[] = {
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, arch)),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, HOST_ARCH, 1, 0),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr)),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, __NR_socket, 0, 5),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, args[0])),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, AF_INET, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EAFNOSUPPORT),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, AF_INET6, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EAFNOSUPPORT),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW)
    };
    struct sock_fprog program = {(unsigned short)(sizeof(rules)/sizeof(rules[0])), rules};
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0) return -1;
    return prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &program);
}

int main(int argc, char **argv) {
    if (argc < 2) { fprintf(stderr, "Usage: network-blocker COMMAND [ARGS...] | --probe\n"); return 2; }
    if (disable_network() != 0) { perror("Cannot install network-blocking seccomp filter"); return 2; }
    if (argc == 2 && strcmp(argv[1], "--probe") == 0) {
        int ipv4 = socket(AF_INET, SOCK_STREAM, 0); int ipv4_error = errno;
        int ipv6 = socket(AF_INET6, SOCK_STREAM, 0); int ipv6_error = errno;
        int local = socket(AF_UNIX, SOCK_STREAM, 0);
        if (local >= 0) close(local);
        if (ipv4 >= 0) close(ipv4);
        if (ipv6 >= 0) close(ipv6);
        printf("{\"ipv4_errno\":%d,\"ipv6_errno\":%d,\"unix_available\":%s}\n",
               ipv4_error, ipv6_error, local >= 0 ? "true" : "false");
        return ipv4 < 0 && ipv6 < 0 && ipv4_error == EAFNOSUPPORT && ipv6_error == EAFNOSUPPORT && local >= 0 ? 0 : 1;
    }
    execvp(argv[1], argv + 1); perror("Cannot execute network-blocked command"); return 127;
}
