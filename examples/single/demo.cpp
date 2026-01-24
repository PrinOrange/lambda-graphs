#include <iostream>

class BaseClass {
public:
    BaseClass() {
        std::cout << "BaseClass constructor\n";
    }
    virtual ~BaseClass() {
        std::cout << "BaseClass destructor\n";
    }

    virtual void mutate(int* k) = 0;
};

namespace NS1 {
class DerivedClass : public BaseClass {
    int ns1_first;
public:
    DerivedClass() {
        std::cout << "NS1::DerivedClass constructor\n";
        ns1_first = 0;
    }
    virtual ~DerivedClass() {
        std::cout << "NS1::DerivedClass destructor\n";
    }

    virtual void mutate(int* k) {
        *k += 1;
        ns1_first += *k;
    }
};
}

namespace NS2 {
class DerivedClass : public BaseClass {
    int ns2_first;
public:
    DerivedClass() {
        std::cout << "NS2::DerivedClass constructor\n";
        ns2_first = 0;
    }
    virtual ~DerivedClass() {
        std::cout << "NS2::DerivedClass destructor\n";
    }

    virtual void mutate(int* k) {
        *k += 1;
        ns2_first += *k;
    }
};
}


int main() {
    NS1::DerivedClass obj_1;
    BaseClass* baseptr = &obj_1;
    int x = 100;
    baseptr->mutate(&x);
    std::cout << x;
}