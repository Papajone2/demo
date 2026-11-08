/*
 * ARMv6 Linux SSD1306 splash. No libc, Python, crypto, keys or heap.
 * The fixed public bitmap is compiled by the existing image provisioning.
 * Python remains the service fallback if this optional executable fails.
 */
#include <asm/unistd.h>

static long call3(long number, long a, long b, long c) {
    register long r0 __asm__("r0") = a;
    register long r1 __asm__("r1") = b;
    register long r2 __asm__("r2") = c;
    register long r7 __asm__("r7") = number;
    __asm__ volatile("svc 0" : "+r"(r0) : "r"(r1), "r"(r2), "r"(r7) : "memory", "cc");
    return r0;
}
static int equal(const char *a, const char *b) {
    while (*a && *a == *b) { a++; b++; }
    return *a == *b;
}
static int write_all(int fd, const unsigned char *data, int size) {
    /* I2C writes are one complete command/message, not a byte-stream retry. */
    return call3(__NR_write, fd, (long)data, size) == size;
}
static const unsigned char init[] = {
    0xae, 0xd5, 0x80, 0xa8, 0x3f, 0xd3, 0, 0x40,
    0x8d, 0x14, 0x20, 0, 0xa1, 0xc8, 0xda, 0x12,
    0x81, 0x7f, 0xd9, 0xf1, 0xdb, 0x40, 0xa4, 0xa6, 0xaf,
    0x21, 0, 127, 0x22, 0, 7
};
static unsigned char frame[1024];
int splash_main(int argc, char **argv) {
    if (argc == 2 && equal(argv[1], "--check")) return sizeof(frame) == 1024 && init[0] == 0xae ? 0 : 1;
    long bitmap = call3(__NR_open, (long)"/opt/satooshi/device/satooshi/assets/splash.bin", 0, 0);
    if (bitmap < 0) return 1;
    int count = 0;
    while (count < 1024) {
        long n = call3(__NR_read, bitmap, (long)(frame + count), 1024 - count);
        if (n <= 0) { call3(__NR_close, bitmap, 0, 0); return 1; }
        count += n;
    }
    unsigned char extra;
    long trailing = call3(__NR_read, bitmap, (long)&extra, 1);
    call3(__NR_close, bitmap, 0, 0);
    if (trailing != 0) return 1;
    for (int attempt = 0; attempt < 30; attempt++) {
        long display = call3(__NR_open, (long)"/dev/i2c-1", 2, 0);
        int ok = display >= 0 && call3(__NR_ioctl, display, 0x0703, 0x3c) >= 0;
        unsigned char packet[33];
        for (unsigned int i = 0; ok && i < sizeof(init); i++) {
            packet[0] = 0; packet[1] = init[i];
            ok = write_all(display, packet, 2);
        }
        for (int start = 0; ok && start < 1024; start += 32) {
            packet[0] = 0x40;
            for (int j = 0; j < 32; j++) packet[j + 1] = frame[start + j];
            ok = write_all(display, packet, 33);
        }
        if (display >= 0) call3(__NR_close, display, 0, 0);
        if (ok) {
            static const unsigned char message[] = "SATOOSHI_BOOT stage=logo_native\n";
            call3(__NR_write, 2, (long)message, sizeof(message) - 1);
            return 0;
        }
        long pause[2] = { 0, 100000000 };
        call3(__NR_nanosleep, (long)pause, 0, 0);
    }
    return 1;
}
__asm__(".global _start\n"
        "_start:\n"
        "ldr r0, [sp]\n"
        "add r1, sp, #4\n"
        "bl splash_main\n"
        "mov r7, #1\n"
        "svc 0\n");
