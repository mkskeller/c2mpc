#!/bin/bash

data_type=sint
oram_type=OptimalORAM

while getopts OgN:I:rapi:o: opt; do
    case $opt in
        O) optimize=1 ;;
	g) data_type=sgf2nint32
	    gf2n=-g
	    ;;
	N) N=$OPTARG
	    clang_args="$clang_args -DN=$OPTARG"
	    mcomp_args="-N $OPTARG"
	    ;;
	I) init_string=$OPTARG ;;
	r) regexp=1 ;;
	a) asm_output=-a ;;
	p) oram_type=AtLeastOneRecursionPackedPathORAM
	    packed=-p
	    ;;
	i) inc_init=$OPTARG ;;
	o) out_dir=$OPTARG ;;
    esac
done

shift $[OPTIND-1]

if test "$regexp"; then
    name=${1%.re}
    prog=$name.c
    re2c $1 > $prog
    cp $1 $1.$(date +%y%m%d-%H%M)
else
    prog=$1
    name=$1$N$gf2n$packed
fi

if test "$asm_output"; then
    mpc_file=/dev/stdout
else
    mpc_file=${out_dir:-.}/$name.mpc
fi


echo name: $name > /dev/stderr
echo prog: $prog > /dev/stderr
echo mpc_file: $mpc_file > /dev/stderr

clang $clang_args -emit-llvm -c $prog

object=${prog%c}o

OPT=${OPT:-opt}

if test $optimize; then
    $OPT -lowerswitch -targetlibinfo -no-aa -tbaa -basicaa -notti -globalopt -ipsccp -deadargelim -basiccg -prune-eh -inline-cost -inline -functionattrs -domtree -early-cse -simplify-libcalls -lazy-value-info -tailcallelim -reassociate -domtree -loops -loop-simplify -licm -scalar-evolution -loop-simplify -memdep -memdep -memcpyopt -sccp -lazy-value-info -domtree -memdep -dse -adce -strip-dead-prototypes -globaldce -preverify -domtree -verify $object > $object.opt
else
    $OPT -lowerswitch $object > $object.opt
fi

mv $object.opt $object

if ! test "$asm_output"; then
    cat > $mpc_file <<EOF
from machine import *
import oram
#oram.optimal_threshold = 2**12
oram.use_insecure_randomness = True
EOF
fi

echo "Compiling $object to $mpc_file" > /dev/stderr
./mcompile.py $mcomp_args $asm_output $object >> $mpc_file

if ! test "$asm_output"; then
    if test "$init_string" -o "$inc_init"; then
	cat >> $mpc_file <<EOF
data = $oram_type(n_vars, $data_type.basic_type, entry_size=(32,))
EOF
	if test "$init_string"; then
	    cat >> $mpc_file <<EOF
for i,c in enumerate("$init_string"):
    data[i] = ord(c)
EOF
	elif test "$inc_init"; then
	    cat >> $mpc_file <<EOF
for i in range($inc_init):
    data[i] = i
EOF
	fi
	cat >> $mpc_file <<EOF
run_code_with_data(code, data, start, $data_type, oram_type=$oram_type)
EOF
    else
	echo "data = run_code(code, n_vars, start, n_global_vars, \
    $data_type, oram_type=$oram_type)" >> $mpc_file
    fi

    echo "print_ln('%s ?= %s', data[check].reveal(), ${2:-1})" >> $mpc_file
fi
