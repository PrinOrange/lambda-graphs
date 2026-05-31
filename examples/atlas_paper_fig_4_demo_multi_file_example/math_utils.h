#ifndef MATH_UTILS_H
#define MATH_UTILS_H

struct MathContext {
    int last_result;
};

int add(int x, int y);
int multiply(int x, int y);
int factorial(int n);

int get_last_result(void);

#endif
