<!-- {% raw %} -->

# List of Things to Improve in the HLSL Language

* Proposal: [NNNN](NNNN-things-to-improve.md)
* Author(s): [Helena Kotas](https://github.com/hekota)
* Status: **Design In Progress**

## Introduction

This document includes a list of features that we might consider removing in a future
version of the HLSL language. It includes things that:
- have unusual syntax or odd behavior
- are remnants of outdated features that are no longer used or relevant
- are construct that are generally considered "not very nice" from a language point of view

## Motivation

We strive to evolve HLSL into a modern shader language. In order to so we need to recognize
odd, outdated or obscure features that are no longer used or that we do not wish to support
going forward.

## List of Things to Improve

### 1. Global variables outside of `cbuffer` context

All global variables declared outside of `cbuffer` context go implicitly into `$Globals` constant buffer. If the variable has an initializer it gets ignored.

We should either require all global variables to be declared withing `cbuffer` context and stop supporting `$Globals`, or we should require any top-level non-static global variable to be declared with `const` and report error if it is initialized.

### 2. Nested `cbuffer` declarations

Nesting of `cbuffer` declarations and allowing functions inside `cbuffer` declaration context.

```c++
cbuffer CB {
  int a;

  cbuffer CB {  // duplicate name ok
    int b;

    int foo(int x) {
        return x * 2*;
    };
  }
};
```

This is equivalent to:

```c++
cbuffer CB {
  int a;
};

cbuffer CB {  // duplicate name ok
  int b;
};

int foo(int x) {
    return x * 2*;
};

```
https://godbolt.org/z/PeW4E3aj3


## Acknowledgments

