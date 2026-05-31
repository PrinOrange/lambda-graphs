class Box {
  int x;
public:
  Box(int v) { x = v + 1; }
  void inc(int& a) { a += x; }
};
int rec(int n) {
  return n ? rec(n - 1) : 0;
}
int main() {
  Box b(3); int k = 0;
  b.inc(k);
  int arr[3] = {1, 2, 3};
  int* p = arr;
  p++;
  int v = *p;
  int (*fp)(int);
  fp = &rec;
  return fp(k);
}
