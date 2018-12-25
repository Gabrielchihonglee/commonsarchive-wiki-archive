#define _GNU_SOURCE

#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

struct page {
    int id;
    const char *start;
    const char *end;
};

static char *comm;

static const char pagestarttag[] = "  <page>";
static const char pageendtag[] = "  </page>\n";
static const char idtag[] = "<id>";

#define if_perror(cond, msg) do { if (cond) { perror(msg); exit(1); } } while (0);

static int page_compare(const struct page *a, const struct page *b) {
    return a->id - b->id;
}

int main(int argc, char *argv[]) {
    comm = argv[0];

    if (argc != 3) {
        fprintf(stderr, "Usage: %s <source.xml> <dest.xml>\n", comm);
        exit(1);
    }

    int srcfd = open(argv[1], O_RDONLY);
    if_perror(srcfd < 0, argv[1]);

    struct stat sb;
    if_perror(fstat(srcfd, &sb), comm);

    size_t size = sb.st_size;

    const char *src = mmap(NULL, size, PROT_READ, MAP_SHARED, srcfd, 0);
    if_perror(src == NULL, comm);

    int numpages = 0;
    {
        const char *haystack = src;
        const char *haystackend = haystack + size;
        while ((haystack = memmem(haystack, haystackend - haystack,
                                  pagestarttag, strlen(pagestarttag)))) {
            haystack++;
            numpages++;
        }
    }

    struct page *pages = calloc(numpages, sizeof(struct page));
    const char *first, *last;
    if_perror(pages == NULL, comm);
    {
        size_t curpage = 0;
        const char *haystack = src;
        const char *haystackend = haystack + size;
        while ((haystack = memmem(haystack, haystackend - haystack,
                                  pagestarttag, strlen(pagestarttag)))) {
            const char *start = haystack;
            const char *end = memmem(haystack, haystackend - haystack,
                                     pageendtag, strlen(pageendtag))
                              + strlen(pageendtag);
            haystack = end;
            int id = atoi(memmem(start, end - start,
                                 idtag, strlen(idtag))
                              + strlen(idtag));
            pages[curpage++] = (struct page){ .id = id, .start = start, .end = end };
        }
        first = pages[0].start;
        last = pages[numpages - 1].end;
    }

    qsort(pages, numpages, sizeof(struct page),
          (int (*)(const void *, const void *))&page_compare);

    int destfd = open(argv[2], O_CREAT | O_RDWR, 0666);
    if_perror(destfd < 0, argv[2]);

    if_perror(ftruncate(destfd, size) < 0, comm);

    char *dest = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, destfd, 0);
    if_perror(dest == NULL, comm);

    {
        memcpy(dest, src, first - src);
        dest += first - src;

        for (size_t i = 0; i < numpages; i++) {
            memcpy(dest, pages[i].start, pages[i].end - pages[i].start);
            dest += pages[i].end - pages[i].start;
        }

        memcpy(dest, last, src + size - last);
    }
}
