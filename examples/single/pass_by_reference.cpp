#include <iostream>

class TestClass {
public:
    int x;
    TestClass(int _x) {
        x = _x + 20;
    }
    void f1(int& a) {
        a += 100;
        a -= x;
    }
};
int main() {
    TestClass obj(30);
    int k = 0;
    obj.f1(k);
    std::cout << k; 
    return 0;
}