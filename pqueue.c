#include <stdio.h>
#include <signal.h>

const int empty = 1 << 30;

int heap[N+1][2];
int idx[N];
int size;

void debug() {
#ifdef DEBUG
  for (int i = 1; i < 16; i++)
    printf("%d: %d %d %d\n", i, heap[i][0], heap[i][1], idx[i]);
  printf("\n");
  for (int i = 0; i < N; i++)
    if (idx[i] < size && heap[idx[i]][1] != i)
      raise(SIGABRT);
#endif
}

void queue_init() {
  for (int i = 0; i < N; i++) {
    heap[i][0] = empty;
    heap[i][1] = empty;
    idx[i] = empty;
  }
  size = 0;
}

void update_idx(int key, int heap_pos) {
  if (key < N) {
    idx[key] = heap_pos;
  }
}

void bubble_up(int child) {
  while (child > 1) {
    int parent = child >> 1;
    if (heap[child][0] < heap[parent][0]) {
	int tmp;
	for (int i = 0; i < 2; i++) {
	  tmp = heap[child][i];
	  heap[child][i] = heap[parent][i];
	  heap[parent][i] = tmp;
	}
	update_idx(heap[parent][1], parent);
	update_idx(heap[child][1], child);
    }
    child = parent;
  }
}

void bubble_down() {
  int parent = 1, children[2], child;
  while (parent < N/2) {
    children[0] = parent << 1;
    children[1] = children[0] + 1;
    child = children[heap[children[0]][0] > heap[children[1]][0]];
    for (int i = 0; i < 2; i++) {
      int tmp = heap[child][i];
      heap[child][i] = heap[parent][i];
      heap[parent][i] = tmp;
    }
    update_idx(heap[parent][1], parent);
    update_idx(heap[child][1], child);
    parent = child;
  }
}

int queue_add(int key, int prio) {
  if (idx[key] == empty) {
    size++;
    heap[size][0] = prio;
    heap[size][1] = key;
    idx[key] = size;
    bubble_up(size);
    return 1;
  }
  else {
    return 0;
  }
}

int queue_pop(int* key, int* prio) {
  if (size > 0) {
    *prio = heap[1][0];
    *key = heap[1][1];
    heap[1][0] = empty;
    heap[1][1] = empty;
    update_idx(*key, empty);
    bubble_down();
    size--;
    return 1;
  }
  else {
    return 0;
  }
}

int queue_decrease(int key, int new_prio) {
  int i = idx[key];
  if (i != empty && heap[i][0] > new_prio) {
    heap[i][0] = new_prio;
    bubble_up(i);
    return 1;
  }
  return 0;
}
