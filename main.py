import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import anthropic
import os

# Claude API 키는 GitHub Actions의 Secrets에서 가져오기
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
        system="당신은 노동 관련 뉴스를 명확하고 간결히 요약하여 인사노무 담당자에게 제공하는 전문가입니다. 요약은 두 문장 이내로 간결히, 실무 시사점은 짧고 명료한 형태로 정리해 주세요. 과도하게 길어지면 (...)로 축약하지 말고 문장을 다듬어서 짧게 표현해주세요.",
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

    print(f"📌 [노무법인 위너스의 오늘의 노동법 브리핑] ({today_str} 기준)\n")

    has_articles = False
    for category, url in rss_feeds.items():
        news_items = fetch_rss_feed(url)
        if news_items:
            has_articles = True
            print(f"▶ {category}\n")
            for item in news_items[:5]:
                summary_implication = claude_summary_and_implication(item['summary'])
                print(f"🔹 {item['title']} (발행일: {item['published']})\n{summary_implication}\n- 바로가기: {item['link']}\n")

    if not has_articles:
        print("현재 최신 기사가 없습니다.\n")

    print("📌 주요 실무 이슈만 엄선했습니다. 노무법인 위너스가 전하는 노동법 최신 소식! 업무에 도움이 되셨다면 주변에도 공유해 주세요. 👍")

if __name__ == "__main__":
    generate_newsletter()
