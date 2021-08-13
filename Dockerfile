FROM ubuntu:14.04
RUN apt-get update
RUN apt-get install -y clang-3.3 llvm-3.3 python3.5 python3-pip wget
RUN LLVM_CONFIG_PATH=/usr/bin/llvm-config-3.3 pip3 install llvmpy
RUN wget https://github.com/data61/MP-SPDZ/releases/download/v0.2.6/mp-spdz-0.2.6.tar.xz
RUN tar xJvf mp-spdz-0.2.6.tar.xz
RUN ln -s mp-spdz-0.2.6 mp-spdz
ADD machine.py mp-spdz/Compiler
ADD compile.sh *.c mcompile.py ./
RUN OPT=opt-3.3 ./compile.sh -N 10 -o mp-spdz/Programs/Source pqueue_test.c
WORKDIR mp-spdz
RUN python3.5 ./compile.py pqueue_test.c10 --insecure
RUN Scripts/tldr.sh
RUN Scripts/setup-ssl.sh
RUN Scripts/rep-field.sh pqueue_test.c10
