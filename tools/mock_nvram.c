/* mock_nvram.c */
/* A freestanding mock library for TP-Link fuzzer */

/* We are compiling with -nostdlib, so we must define basic types and functions if needed */
/* QEMU User Mode will load this via LD_PRELOAD */

#define NULL ((void*)0)

/* Mock generic NVRAM functions */
/* These prevent crashes when the binary tries to read configuration from NVRAM */

/* Simple strcmp implementation since we don't have libc */
int my_strcmp(const char *s1, const char *s2) {
    while (*s1 && (*s1 == *s2)) {
        s1++;
        s2++;
    }
    return *(const unsigned char *)s1 - *(const unsigned char *)s2;
}

char *nvram_get(const char *key) {
    /* Return safe defaults for common keys */
    if (!key) return "";
    
    /* uhttpd sysmode check */
    if (my_strcmp(key, "sysmode") == 0) return "router";
    
    /* Network defaults */
    if (my_strcmp(key, "lan_ipaddr") == 0) return "192.168.1.1";
    if (my_strcmp(key, "lan_netmask") == 0) return "255.255.255.0";
    
    return ""; /* Return empty string for others to avoid NULL deref */
}

int nvram_match(const char *key, const char *val) {
    char *k = nvram_get(key);
    if (k && val && my_strcmp(k, val) == 0) return 1;
    return 0;
}

int nvram_set(const char *key, const char *val) {
    return 0;
}

int nvram_get_state(const char *key) {
    return 0;
}

/* Mock UBUS functions */
/* uhttpd fails if it cannot connect to ubus. */
/* However, we are now using REAL ubusd, so we don't strictly need these mocks active */
/* UNLESS ubus_connect fails fallback. */
/* harness.py ensures real ubusd is running, so these might be ignored if libubus is loaded effectively */
/* But keeping them safe just in case LD_PRELOAD takes precedence over libubus symbols */

/* Wait! If we LD_PRELOAD this, and it defines ubus_connect, the REAL uhttpd will call THIS ubus_connect */
/* instead of the real libubus.so ubus_connect. */
/* This would BREAK the real connection we worked so hard to fix! */
/* We should REMOVE ubus mocks if we want real ubusd connection. */
/* OR execute them only if we want to mock execution without ubusd. */

/* CRITICAL: Removed ubus mocks to allow real libubus.so to work! */

/* Mock setsockopt */
/* miniupnpd fails on IP_ADD_MEMBERSHIP for SSDP. We fake success. */
int setsockopt(int sockfd, int level, int optname, const void *optval, int optlen) {
    /* Log? No easy way to log without libc printf/write. */
    /* Just return 0 (Success) */
    return 0;
}
int iptables(const char *command) {
    return 0;
}

/* startup banner */
void _init() {
    /* No easy way to print without write(), inline assembly syscall? */
    /* Just silent start */
}
