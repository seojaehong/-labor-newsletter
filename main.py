import sys

# 이 메시지는 표준 에러로 보내지므로 error.log 파일에 저장될 것입니다.
print("Testing explicit exit code 1", file=sys.stderr)

# 스크립트를 오류 상태 (코드 1)로 종료
sys.exit(1)
