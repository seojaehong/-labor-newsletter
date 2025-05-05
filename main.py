import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import anthropic
import os
import smtplib
from email.mime.text import MIMEText

anthropic_client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

today = datetime.today()
today_str = today.strftime("%Y년 %m월 %d일")

def fetch_rss_feed(url):
    feed = feedparser.parse(url)
    news = []
    for entry in feed.entries:
        try:
            published = datetime.strptime(entry.published, '%a, %d %b %Y %H:%M:%S %Z')
        except:
            published = datetime.today()

        if today - published <= timedelta(days=3):
            summary_soup = BeautifulSoup(entry.summary, "html.parser")
            summary_text = summary_soup.get_text().strip()
            news.append({
                "title": entry.title.replace("[.txt]", ""),
                "link": entry.link,
                "published": published.strftime('%Y-%m-%d %H:%M'),
                "summary": summary_text
            })
    return news

def claude_summary_and_implication(content):
    prompt = f"""다음 뉴스를 읽고, 양식에 맞춰 작성해 주세요.

[핵심 요약] (2문장 내외):
-

[실무 시사점] (2-3가지):
-

뉴스 내용:
{content}
"""
    response = anthropic_client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=400,
        temperature=0.2,
        system="당신은 노동 관련 뉴스를 명확하고 간결히 요약하여 인사노무 담당자에게 제공하는 전문가입니다. 요약은 두 문장 이내로 간결히, 실무 시사점은 짧고 명료한 형태로 정리해 주세요.",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text.strip()

def generate_newsletter():
    rss_feeds = {
        "사건/사고": "https://rss.app/feeds/5wPlBHdpqAJmIchh.xml",
        "노동정책": "https://rss.app/feeds/G6EBProFzjCISBt2.xml",
        "노동조합": "https://rss.app/feeds/c9pv5qpCmgYEROxT.xml",
        "노사관계": "https://rss.app/feeds/JaS17kFMTvYda6QG.xml",
        "노동법": "https://rss.app/feeds/YuTCnwc6CzBa5CIR.xml",
        "한겨레 노동뉴스": "https://rss.app/feeds/teZ7fkbACRalryLf.xml"
    }

    newsletter = f"📌 [노무법인 위너스의 오늘의 노동법 브리핑] ({today_str} 기준)\n\n"

    has_articles = False
    for category, url in rss_feeds.items():
        news_items = fetch_rss_feed(url)
        if news_items:
            has_articles = True
            newsletter += f"▶ {category}\n\n"
            for item in news_items[:5]:
                summary_implication = claude_summary_and_implication(item['summary'])
                newsletter += f"🔹 {item['title']} (발행일: {item['published']})\n{summary_implication}\n- 바로가기: {item['link']}\n\n"

    if not has_articles:
        newsletter += "현재 최신 기사가 없습니다.\n\n"

    newsletter += "📌 주요 실무 이슈만 엄선했습니다. 노무법인 위너스가 전하는 노동법 최신 소식! 업무에 도움이 되셨다면 주변에도 공유해 주세요. 👍\n"
    
    return newsletter

# 이메일 발송 함수 추가
def send_email(subject, body, to_email):
    from_email = os.environ['EMAIL_ADDRESS']
    password = os.environ['EMAIL_PASSWORD']

    msg = MIMEText(body, 'plain', 'utf-8')
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(from_email, password)
        smtp.sendmail(from_email, to_email, msg.as_string())

# 뉴스레터 생성 및 이메일 발송 실행
if __name__ == "__main__":
    newsletter_content = generate_newsletter()
    send_email(
        subject=f"[노무법인 위너스] 오늘의 노동법 브리핑 ({today_str})",
        body=newsletter_content,
        to_email=os.environ['EMAIL_ADDRESS']
    )

    print(newsletter_content)  # GitHub Action에서 로그로도 확인할 수 있게 출력
