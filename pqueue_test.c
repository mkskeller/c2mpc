#include "pqueue.c"

int main() {
  queue_init();
  for (int i = 10; i > 0; i--)
    queue_add(i,i);
  debug();
  queue_decrease(10,0);
  debug();
  int res,_;
  queue_pop(&res, &_);
  debug();
  queue_pop(&res, &_);
  debug();
  return res;
}
