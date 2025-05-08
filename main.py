import sys
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import google.generativeai as genai
import os
import smtplib
from email.mime.text import MIMEText
import re
import pytz
import traceback

# 스크립트 시작을 알립니다
print("✅ 스크립트 실행 시작!", file=sys.stderr)

try:
    # 상수 정의
    MAX_ARTICLES = 10  # 뉴스레터에 포함할 최대 기사 수
    
    # 1. 시간대 설정
    try:
        print("시간대 설정 시도...", file=sys.stderr)
        UTC = pytz.timezone('UTC')
        KST = pytz.timezone('Asia/Seoul')
        print("✅ 시간대 설정 완료", file=sys.stderr)
    except Exception as e:
        print(f"❌ 시간대 설정 실패: {e}", file=sys.stderr)
        print("대체 시간대 사용으로 전환합니다", file=sys.stderr)
        from datetime import timezone
        UTC = timezone.utc
    
    # 2. 현재 날짜 설정
    try:
        now_utc = datetime.now(UTC)
        now_kst = datetime.now(KST) if 'KST' in locals() else now_utc.replace(tzinfo=UTC).astimezone(timezone(timedelta(hours=9)))
        today_str = now_kst.strftime("%Y년 %m월 %d일")
        print(f"✅ 현재 날짜: {today_str}", file=sys.stderr)
    except Exception as e:
        print(f"❌ 날짜 설정 오류: {e}", file=sys.stderr)
        today_str = datetime.now().strftime("%Y년 %m월 %d일")
    
    # 3. Gemini API 설정
    try:
        print("Gemini API 설정 시도...", file=sys.stderr)
        api_key = os.environ.get('GOOGLE_API_KEY')
        if not api_key:
            raise ValueError("GOOGLE_API_KEY 환경 변수가 없습니다")
        
        genai.configure(api_key=api_key)
        
        # 간단한 API 테스트
        model = genai.GenerativeModel("gemini-1.5-flash")
        test = model.generate_content("Hello")
        print(f"✅ Gemini API 연결 성공: {test.text[:15]}...", file=sys.stderr)
    except Exception as e:
        print(f"❌ Gemini API 설정 실패: {e}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        raise RuntimeError("Gemini API 연결 필수") from e
    
    # 4. 기본 함수 정의
    def clean_html(html_text):
        """HTML 태그와 엔티티를 제거합니다."""
        if not isinstance(html_text, str):
            return ""
        
        try:
            soup = BeautifulSoup(html_text, "html.parser")
            text = soup.get_text()
            text = re.sub(r'&[a-zA-Z]+;', ' ', text)  # HTML 엔티티 제거
            return ' '.join(text.split())  # 다중 공백 제거 및 정리
        except Exception as e:
            print(f"❌ HTML 정리 실패: {e}", file=sys.stderr)
            return html_text if isinstance(html_text, str) else ""
    
    def get_date_from_entry(entry):
        """피드 항목에서 발행일을 추출합니다."""
        # 기본값: UTC 현재 시각
        now = datetime.now(UTC)
        
        try:
            # 1. published_parsed 사용 (가장 안정적)
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                # struct_time 튜플을 datetime으로 변환
                dt = datetime.fromtimestamp(0)  # 초기값
                try:
                    # 연, 월, 일, 시, 분, 초만 사용
                    dt = datetime(
                        entry.published_parsed[0],  # 연
                        entry.published_parsed[1],  # 월
                        entry.published_parsed[2],  # 일
                        entry.published_parsed[3],  # 시
                        entry.published_parsed[4],  # 분
                        entry.published_parsed[5],  # 초
                    )
                    # UTC timezone 추가
                    dt = dt.replace(tzinfo=UTC)
                    return dt
                except Exception as e:
                    print(f"⚠️ published_parsed 변환 실패: {e}", file=sys.stderr)
            
            # 2. published 문자열 사용
            if hasattr(entry, 'published') and entry.published:
                date_str = entry.published
                
                # RFC 822 형식 시도 (일반적인 RSS)
                try:
                    # 'Wed, 08 May 2025 12:30:00 +0900' 형식
                    formats = [
                        '%a, %d %b %Y %H:%M:%S %z',
                        '%a, %d %b %Y %H:%M:%S %Z',
                        '%a, %d %b %Y %H:%M:%S',
                        '%Y-%m-%dT%H:%M:%S%z',
                        '%Y-%m-%dT%H:%M:%S'
                    ]
                    
                    for fmt in formats:
                        try:
                            dt = datetime.strptime(date_str, fmt)
                            # timezone 정보가 없으면 UTC로 설정
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=UTC)
                            return dt
                        except ValueError:
                            continue
                    
                    print(f"⚠️ 날짜 형식 인식 실패: {date_str}", file=sys.stderr)
                    return now
                except Exception as e:
                    print(f"⚠️ 날짜 문자열 파싱 오류: {e} - {date_str}", file=sys.stderr)
                    return now
        
        except Exception as e:
            print(f"⚠️ 날짜 처리 중 예외 발생: {e}", file=sys.stderr)
        
        # 문제 발생 시 현재 시각 반환
        return now
    
    def fetch_rss_feeds():
        """모든 RSS 피드에서 최신 기사를 가져옵니다."""
        # RSS 피드 목록
        rss_feeds = {
            "사건/사고": "https://rss.app/feeds/5wPlBHdpqAJmIchh.xml",
            "노동정책": "https://rss.app/feeds/G6EBProFzjCISBt2.xml",
            "노동조합": "https://rss.app/feeds/c9pv5qpCmgYEROxT.xml",
            "노사관계": "https://rss.app/feeds/JaS17kFMTvYda6QG.xml",
            "노동법": "https://rss.app/feeds/YuTCnwc6CzBa5CIR.xml",
            "한겨레 노동뉴스": "https://rss.app/feeds/teZ7fkbACRalryLf.xml"
        }
        
        print(f"RSS 피드 {len(rss_feeds)}개 가져오기 시작...", file=sys.stderr)
        all_articles = []
        processed_urls = set()  # 중복 URL 방지
        
        # 3일 전 기준점 설정 (UTC)
        cutoff_date = datetime.now(UTC) - timedelta(days=3)
        
        for category, url in rss_feeds.items():
            try:
                print(f"피드 가져오는 중: {category}", file=sys.stderr)
                feed = feedparser.parse(url)
                
                if not hasattr(feed, 'entries'):
                    print(f"⚠️ '{category}' 피드에 항목이 없습니다", file=sys.stderr)
                    continue
                
                print(f"✅ '{category}' 피드에서 {len(feed.entries)}개 항목 발견", file=sys.stderr)
                
                for entry in feed.entries:
                    # 필수 데이터 확인
                    if not hasattr(entry, 'title') or not hasattr(entry, 'link'):
                        continue
                    
                    # 중복 방지
                    link = entry.link.strip() if hasattr(entry, 'link') else ""
                    if not link or link in processed_urls:
                        continue
                    
                    # 발행일 파싱
                    published_date = get_date_from_entry(entry)
                    
                    # 3일 이내 기사만 포함
                    if published_date < cutoff_date:
                        continue
                    
                    # 제목과 요약 정리
                    title = clean_html(entry.title) if hasattr(entry, 'title') else "제목 없음"
                    
                    # 요약 추출
                    summary = ""
                    if hasattr(entry, 'summary'):
                        summary = clean_html(entry.summary)
                    elif hasattr(entry, 'content'):
                        content_list = entry.content if isinstance(entry.content, list) else []
                        for content_item in content_list:
                            if isinstance(content_item, dict) and 'value' in content_item:
                                summary = clean_html(content_item['value'])
                                break
                    
                    # 유효한 기사만 추가
                    if title != "제목 없음" and link and summary:
                        all_articles.append({
                            'title': title,
                            'link': link,
                            'published': published_date,  # UTC aware datetime
                            'summary': summary,
                            'category': category
                        })
                        processed_urls.add(link)
            
            except Exception as e:
                print(f"❌ '{category}' 피드 처리 중 오류: {e}", file=sys.stderr)
                print(traceback.format_exc(), file=sys.stderr)
        
        print(f"✅ 총 {len(all_articles)}개 유효 기사 수집 완료", file=sys.stderr)
        return all_articles
    
    def select_articles(all_articles):
        """뉴스레터에 포함할 기사를 선택합니다."""
        # 최신순 정렬
        all_articles.sort(key=lambda x: x['published'], reverse=True)
        
        # 시간 기준점 설정
        now = datetime.now(UTC)
        threshold_24h = now - timedelta(hours=24)
        threshold_2days = now - timedelta(days=2)
        
        # 선택된 기사
        selected = []
        
        # 1. 최근 24시간 기사 먼저 선택
        articles_24h = [a for a in all_articles if a['published'] >= threshold_24h]
        selected.extend(articles_24h)
        
        # 2. 5개 미만이면 2일 이내 기사 추가
        if len(selected) < 5:
            articles_2days = [
                a for a in all_articles 
                if threshold_24h > a['published'] >= threshold_2days
            ]
            needed = min(5 - len(selected), len(articles_2days))
            selected.extend(articles_2days[:needed])
        
        # 3. 여전히 5개 미만이면 3일 이내 나머지 기사 추가
        if len(selected) < 5:
            remaining = [
                a for a in all_articles 
                if a['published'] < threshold_2days and a not in selected
            ]
            needed = min(5 - len(selected), len(remaining))
            selected.extend(remaining[:needed])
        
        # 최대 기사 수 제한
        return selected[:MAX_ARTICLES]
    
    def summarize_with_gemini(content):
        """Gemini API로 기사 내용을 요약합니다."""
        if not content or len(content.strip()) < 50:
            return "[핵심 요약]\n- 내용이 너무 짧거나 없습니다.\n\n[실무 시사점]\n- 해당 없음."
        
        # 내용 길이 제한
        max_length = 6000
        if len(content) > max_length:
            content = content[:max_length] + "..."
        
        prompt = f"""다음 뉴스를 읽고, 인사노무 담당자가 바로 이해하고 실무에 적용할 수 있도록 아래 양식에 맞춰 간결하게 작성해 주세요. 불필요한 서론이나 결론 없이 양식 내용만 바로 출력해 주세요.

[핵심 요약] (2문장 이내로, 뉴스 내용을 간결하게 요약)
- 

[실무 시사점] (2-3가지, 구체적으로 어떤 점을 주의하거나 대비해야 하는지 명확하게 제시)
- 

뉴스 내용:
{content}
"""
        
        try:
            model = genai.GenerativeModel("gemini-1.5-pro-latest")
            response = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.2,
                    max_output_tokens=600,
                )
            )
            
            if hasattr(response, 'text') and response.text:
                return response.text.strip()
            else:
                return "[핵심 요약]\n- 요약 생성에 실패했습니다.\n\n[실무 시사점]\n- 생성에 실패했습니다."
        
        except Exception as e:
            print(f"❌ Gemini 요약 생성 오류: {e}", file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)
            return "[핵심 요약]\n- 요약 생성 중 오류가 발생했습니다.\n\n[실무 시사점]\n- 시스템 오류로 생성에 실패했습니다."
    
    def create_newsletter():
        """뉴스레터를 생성합니다."""
        print("뉴스레터 생성 시작...", file=sys.stderr)
        
        # 1. RSS 피드에서 기사 가져오기
        all_articles = fetch_rss_feeds()
        
        if not all_articles:
            print("⚠️ 수집된 기사가 없습니다", file=sys.stderr)
            newsletter = f"""📌 [노무법인 위너스의 오늘의 노동법 브리핑] ({today_str} 기준)

현재 최신 기사가 없습니다 (최대 최근 3일 이내 기사 기준).

📌 주요 실무 이슈만 엄선했습니다. 노무법인 위너스가 전하는 노동법 최신 소식! 업무에 도움이 되셨다면 주변에도 공유해 주세요. 👍
"""
            return newsletter
        
        # 2. 기사 선택
        selected_articles = select_articles(all_articles)
        print(f"✅ {len(selected_articles)}개 기사 선택 완료", file=sys.stderr)
        
        # 3. 뉴스레터 헤더
        newsletter = f"""📌 [노무법인 위너스의 오늘의 노동법 브리핑] ({today_str} 기준)

"""
        
        # 4. 각 기사 요약 및 추가
        for i, article in enumerate(selected_articles):
            print(f"기사 {i+1}/{len(selected_articles)} 요약 중: {article['title'][:30]}...", file=sys.stderr)
            
            # 발행일 KST로 변환
            try:
                published_kst = article['published'].astimezone(KST if 'KST' in locals() else timezone(timedelta(hours=9)))
                published_str = published_kst.strftime('%Y-%m-%d %H:%M')
            except Exception as e:
                print(f"⚠️ 날짜 변환 오류: {e}", file=sys.stderr)
                published_str = article['published'].strftime('%Y-%m-%d %H:%M UTC')
            
            # Gemini로 요약 생성
            summary = summarize_with_gemini(article['summary'])
            
            # 뉴스레터에 추가
            newsletter += f"""🔹 {article['title']} (발행일: {published_str})
{summary}
- 바로가기: {article['link']}

"""
        
        # 5. 뉴스레터 푸터
        newsletter += """📌 주요 실무 이슈만 엄선했습니다. 노무법인 위너스가 전하는 노동법 최신 소식! 업무에 도움이 되셨다면 주변에도 공유해 주세요. 👍"""
        
        print("✅ 뉴스레터 생성 완료", file=sys.stderr)
        return newsletter
    
    def send_email(subject, body, to_email):
        """이메일을 발송합니다."""
        print("이메일 발송 준비...", file=sys.stderr)
        
        # 환경 변수 확인
        email_from = os.environ.get('EMAIL_ADDRESS')
        email_password = os.environ.get('EMAIL_PASSWORD')
        
        if not email_from or not email_password:
            print("❌ 이메일 계정 정보가 없습니다", file=sys.stderr)
            return False
        
        try:
            print(f"이메일 발송 시도: to={to_email}", file=sys.stderr)
            
            # 메시지 생성
            msg = MIMEText(body, 'plain', 'utf-8')
            msg['Subject'] = subject
            msg['From'] = email_from
            msg['To'] = to_email
            
            # SMTP 연결 및 전송
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
                smtp.login(email_from, email_password)
                smtp.send_message(msg)
            
            print("✅ 이메일 발송 성공!", file=sys.stderr)
            return True
        
        except Exception as e:
            print(f"❌ 이메일 발송 실패: {e}", file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)
            return False
    
    # 메인 실행 흐름
    print("====== 메인 프로세스 시작 ======", file=sys.stderr)
    
    # 1. 뉴스레터 생성
    newsletter_content = create_newsletter()
    
    # 2. 뉴스레터 출력 (파일로 저장됨)
    print(newsletter_content)  # 이 출력이 newsletter.txt로 리다이렉트됨
    
    # 3. 이메일 발송 (선택적)
    recipient = os.environ.get('EMAIL_ADDRESS')
    if recipient:
        send_email(
            subject=f"[노무법인 위너스] 오늘의 노동법 브리핑 ({today_str})",
            body=newsletter_content,
            to_email=recipient
        )
    else:
        print("⚠️ 이메일 주소가 설정되지 않아 이메일 발송을 건너뜁니다", file=sys.stderr)
    
    print("====== 메인 프로세스 완료 ======", file=sys.stderr)

except Exception as e:
    print(f"❌❌❌ 스크립트 실행 중 치명적인 오류 발생: {e}", file=sys.stderr)
    print(traceback.format_exc(), file=sys.stderr)
    sys.exit(1)  # 오류 코드로 종료

print("✅✅✅ 스크립트 정상 종료", file=sys.stderr)
