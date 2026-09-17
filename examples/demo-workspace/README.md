# demo-workspace

A tiny in-repo target repository used by the M1 end-to-end acceptance (T1-15).

It exists so the documented question "用户令牌在哪里校验" has a real answer in
indexed code: src/auth/token.py. The index directory .coderag is gitignored.

Index it from this directory:

    python -m dsh_coderag index .
