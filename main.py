import sys

# 이 메시지가 표준 에러로 출력되어 error.log 파일에 저장되어야 합니다.
print("Basic script started.", file=sys.stderr)

# 스크립트가 오류 없이 이 지점까지 실행된다면 exit code 0으로 정상 종료될 것입니다.
