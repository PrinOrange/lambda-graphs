// Main file for --code-folder testing
#include <stdio.h>
#include "utils.h"

int main() {
    int a = 10;
    int b = 20;

    int sum = add(a, b);
    int diff = subtract(a, b);

    printf("Sum: %d\n", sum);
    printf("Difference: %d\n", diff);

    return 0;
}
