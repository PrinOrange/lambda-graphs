#include <stdio.h>
#include "math_utils.h"

int main(void) {
    int f = factorial(5);
    int last = get_last_result();
    printf("fact=%d last=%d\n", f, last);
    return 0;
}
