import sys
import os
import datetime
import traceback

# 실행 시간 기록을 위한 설정
start_time = datetime.datetime.now()

def log(message):
    """진행 상황을 stderr에 출력합니다"""
    elapsed = datetime.datetime.now() - start_time
    print(f"[{elapsed.total_seconds():.1f}초] {message}", file=sys.stderr)

try:
    log("스크립트 시작")
    
    # 기본 환경 설정 확인
    log("환경 설정 확인")
    log(f"Python 버전: {sys.version}")
    
    # 환경 변수 확인
    api_key = os.environ.get('GOOGLE_API_KEY')
    email = os.environ.get('EMAIL_ADDRESS')
    log(f"API 키 설정: {'예' if api_key else '아니오'}")
    log(f"이메일 설정: {'예' if email else '아니오'}")
    
    # 외부 모듈 로드 시도
    log("필수 모듈 로드 시도...")
    
    # 1. feedparser - RSS 피드
    try:
        import feedparser
        log("✓ feedparser 로드 성공")
    except ImportError as e:
        log(f"✗ feedparser 로드 실패: {e}")
    
    # 2. BeautifulSoup - HTML 파싱
    try:
        from bs4 import BeautifulSoup
        log("✓ BeautifulSoup 로드 성공")
    except ImportError as e:
        log(f"✗ BeautifulSoup 로드 실패: {e}")
    
    # 3. pytz - 시간대 처리
    try:
        import pytz
        log("✓ pytz 로드 성공")
    except ImportError as e:
        log(f"✗ pytz 로드 실패: {e}")
    
    # 4. google.generativeai - Gemini API
    try:
        import google.generativeai as genai
        log("✓ google.generativeai 로드 성공")
        
        # Gemini API 설정 테스트 (가장 빠른 모델로)
        genai.configure(api_key=api_key)
        log("Gemini API 설정 완료, 연결 테스트 시도...")
        
        # 간단한 API 호출 시도 (타임아웃 설정)
        # 저사양 모델로 짧은 메시지 생성
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content("Hello, World!")
        log(f"✓ Gemini API 응답 성공: {response.text[:20]}...")
    except Exception as e:
        log(f"✗ Gemini API 오류: {e}")
        log(traceback.format_exc())
    
    # 실제로 사용할 RSS 피드 하나만 테스트
    log("RSS 피드 테스트...")
    test_url = "https://rss.app/feeds/5wPlBHdpqAJmIchh.xml"  # 사건/사고 피드
    
    try:
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        
        # 재시도 및 타임아웃 설정
        session = requests.Session()
        retry = Retry(total=3, backoff_factor=0.5)
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        
        # 헤드 요청만으로 접근성 확인 (타임아웃 5초)
        response = session.head(test_url, timeout=5)
        log(f"✓ RSS 피드 접근 가능: 상태 코드={response.status_code}")
        
        # 실제 피드 내용 가져오기 (타임아웃 10초)
        feed = feedparser.parse(test_url)
        feed_entries = len(feed.entries) if hasattr(feed, 'entries') else 0
        log(f"✓ RSS 피드 파싱 성공: {feed_entries}개 항목 발견")
    except Exception as e:
        log(f"✗ RSS 피드 오류: {e}")
        log(traceback.format_exc())
    
    # 테스트 뉴스레터 생성
    newsletter = f"""📌 [노무법인 위너스의 오늘의 노동법 브리핑] (테스트)

이것은 디버깅을 위한 테스트 뉴스레터입니다.
실제 기사 대신 이 메시지가 표시됩니다.

📌 주요 실무 이슈만 엄선했습니다. 노무법인 위너스가 전하는 노동법 최신 소식!
"""
    
    # 결과 출력
    print(newsletter)  # 이 출력이 newsletter.txt에 저장됨
    
    log("스크립트 실행 완료!")

except Exception as e:
    log(f"치명적인 오류 발생: {e}")
    log(traceback.format_exc())
    sys.exit(1)
