Software implementing the [oblivious
machine](https://eprint.iacr.org/2015/467). Use Docker to set up a
container and run an example:
```
docker build .
```

The Docker container uses Ubuntu 14.04 because the software uses
[llvmpy](http://www.llvmpy.org), which in turn relies on LLVM 3.3. You
should be able to run the software on later versions if you install
LLVM 3.3, however.
