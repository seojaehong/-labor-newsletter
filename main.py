# -*- coding: utf-8 -*-
import sys

# 이 메시지는 표준 출력으로 보내지므로 newsletter.txt 파일에 저장될 것입니다.
print("Hello standard output")

# 이 메시지는 표준 에러로 보내지므로 error.log 파일에 저장될 것입니다.
print("Hello standard error", file=sys.stderr)

# 스크립트가 자연스럽게 종료되도록 sys.exit(0)는 사용하지 않습니다.
