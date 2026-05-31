#include "math_utils.h"

static struct MathContext ctx = { 0 };

int add(int x, int y) {
    int r = x + y;
    ctx.last_result = r;
    return r;
}

int multiply(int x, int y) {
    int r = 0;
    int i = 0;
    while (i < y) {
        r = add(r, x);
        i = i + 1;
    }
    ctx.last_result = r;
    return r;
}

int factorial(int n) {
    int r = 1;
    int i = 1;
    while (i <= n) {
        r = multiply(r, i);
        i = i + 1;
    }
    ctx.last_result = r;
    return r;
}

int get_last_result(void) {
    return ctx.last_result;
}
