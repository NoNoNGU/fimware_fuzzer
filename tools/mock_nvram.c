/* 
   Mock NVRAM library for TP-Link Firmware Fuzzing
   FREESTANDING VERSION (No libc dependencies)
   
   Fixed: Replaced all strcmp calls with my_strcmp
*/

// Minimal string functionality
int my_strcmp(const char *s1, const char *s2) {
    while (*s1 && (*s1 == *s2)) {
        s1++;
        s2++;
    }
    return *(const unsigned char *)s1 - *(const unsigned char *)s2;
}

// Global hook
char *nvram_get(const char *key) {
    if (!key) return 0;

    // Direct string literals are stored in .rodata, safe to return
    if (my_strcmp(key, "ip_addr") == 0) return "192.168.0.1";
    if (my_strcmp(key, "lan_ip") == 0) return "192.168.0.1";
    if (my_strcmp(key, "lan_mask") == 0) return "255.255.255.0";
    if (my_strcmp(key, "Login") == 0) return "admin";
    if (my_strcmp(key, "Password") == 0) return "admin";
    
    // The key that was failing
    if (my_strcmp(key, "sysmode") == 0) return "router";

    // Default safe return (empty string)
    return ""; 
}

int nvram_match(char *key, char *val) {
    char *ret = nvram_get(key);
    if (!ret) return 0;
    return (my_strcmp(ret, val) == 0);
}

int nvram_set(const char *key, const char *value) {
    return 0;
}

int nvram_get_state(char *key) {
    return 0;
}

// Mock other functions that might be used
int nvram_load(void) { return 0; }
int nvram_commit(void) { return 0; }
