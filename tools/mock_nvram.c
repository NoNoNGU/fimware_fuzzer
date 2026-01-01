/* 
   Mock Library for TP-Link Firmware Fuzzing
   FREESTANDING VERSION (No libc dependencies)
*/

int my_strcmp(const char *s1, const char *s2) {
    while (*s1 && (*s1 == *s2)) {
        s1++;
        s2++;
    }
    return *(const unsigned char *)s1 - *(const unsigned char *)s2;
}

// ------------------------------------------------------------------
// NVRAM Mocks
// ------------------------------------------------------------------
char *nvram_get(const char *key) {
    if (!key) return 0;
    if (my_strcmp(key, "ip_addr") == 0) return "192.168.0.1";
    // ... (other keys omitted for brevity, logic same)
    if (my_strcmp(key, "sysmode") == 0) return "router";
    return ""; 
}

int nvram_match(char *key, char *val) {
    char *ret = nvram_get(key);
    if (!ret) return 0;
    return (my_strcmp(ret, val) == 0);
}
int nvram_set(const char *key, const char *value) { return 0; }
int nvram_get_state(char *key) { return 0; }
int nvram_load(void) { return 0; }
int nvram_commit(void) { return 0; }

// ------------------------------------------------------------------
// UBUS Mocks
// ------------------------------------------------------------------

// Static buffer to act as the "struct ubus_context"
// Using a large enough buffer prevents segfaults if they access fields.
static char fake_ctx[4096];

void *ubus_connect(const char *path) {
    // Return a valid pointer to writable memory
    return (void *)fake_ctx;
}

int ubus_add_uloop(void *ctx) {
    return 0;
}

void ubus_free(void *ctx) {
    return;
}
