#include <iostream>
void f1(int times) {
    if(!times)
        return;
    std::cout << "In f1()\n";
    f1(times-1);
}
void f2() {
    std::cout << "In f2()\n";
}
int main() {
    void (*fptr_1)(int);
    void (*fptr_2)(void);
    fptr_1 = &f1;
    fptr_2 = &f2;

    int var = 0;
    std::cin >> var;
    (var > 0) ? fptr_1(3) : fptr_2();
}