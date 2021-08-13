#include <stdio.h>
#include <signal.h>

#include "pqueue.c"

struct Edge {
  int u;
  int v;
  int weight;
};

const int inf = empty;

void debug_setup(struct Edge* edges, int* e_index) {
#ifdef DEBUG
  for (int i = 0; i < N; i++)
    printf("%d: %d\n", i, e_index[i]);
  for (int i = 0; i < 2*N; i++) {
    printf("(%d,%d): %d\n", edges[i].u, edges[i].v, edges[i].weight);
  }
  printf("\n");
#endif
}

void debug_result(int *dist, int* prev) {
#ifdef DEBUG
  for (int i = 0; i < N; i++) {
    printf("%d: %d %d\n", i, dist[i], prev[i]);
  }
  if (dist[N-1] != 1)
    raise(SIGABRT);
  if (dist[N/2] != N/2)
    raise(SIGABRT);
  if (prev[N-1] != 0)
    raise(SIGABRT);
#endif
}

int main() {
  struct Edge edges[2*N];
  int e_index[N];

  for (int i = 1; i < N; i++) {
    edges[2*i].u = i;
    edges[2*i].v = i - 1;
    edges[2*i].weight = 1;
  }

  for (int i = 0; i < N - 1; i++) {
    edges[2*i+1].u = i;
    edges[2*i+1].v = i + 1;
    edges[2*i+1].weight = 1;
    e_index[i] = 2*i;
  }

  edges[0].u = 0;
  edges[0].v = N - 1;
  edges[0].weight = 1;
  edges[2*N-1].u = N - 1;
  edges[2*N-1].v = 0;
  edges[2*N-1].weight = 1;
  e_index[N-1] = 2*(N - 1);

  debug_setup(edges, e_index);

  int dist[N], prev[N];

  int source = 0;
  dist[source] = 0;
  prev[source] = 0;
  queue_init();

  for (int v = 0; v < N; v++) {
    if (v != source) {
      dist[v] = inf;
      prev[v] = inf;
    }
    queue_add(v, dist[v]);
  }

  while (size) {
    int u,_;
    queue_pop(&u, &_);
    int i = e_index[u];
    while (edges[i].u == u) {
      int v = edges[i].v;
      int alt = dist[u] + edges[i].weight;
      if (alt < dist[v]) {
	dist[v] = alt;
	prev[v] = u;
	queue_decrease(v, alt);
      }
      i++;
    }
  }

  debug_result(dist, prev);

  return dist[N/2+1];
}
