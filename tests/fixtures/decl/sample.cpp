#include <vector>

class Pool {
public:
    int acquire() { return 1; }
};

struct Point {
    int x;
    int y;
};

int add(int a, int b) {
    return a + b;
}
