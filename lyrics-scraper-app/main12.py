import requests
from bs4 import BeautifulSoup
import pandas as pd
import time

def extract_song_info_from_page(song_url, song_title):
    response = requests.get(song_url)
    soup = BeautifulSoup(response.text, "html.parser")

    # 歌詞取得
    lyrics_div = soup.find("div", class_="hiragana")
    lyrics = lyrics_div.text.strip() if lyrics_div else "歌詞が見つかりませんでした"

    # メタ情報初期化
    meta_info = {
        "release_date": "",
        "lyricist": "",
        "composer": "",
        "arranger": ""
    }

    # 親ブロック：dl.newLyricWork
    info_dl = soup.find("dl", class_="newLyricWork")
    if info_dl:
        children = list(info_dl.children)
        label = None
        for tag in children:
            if tag.name == "dd" and "newLyricWork__date" in tag.get("class", []):
                meta_info["release_date"] = tag.text.strip()
            elif tag.name == "dt" and "newLyricWork__title" in tag.get("class", []):
                label = tag.text.strip()
            elif tag.name == "dd" and "newLyricWork__body" in tag.get("class", []) and label:
                names = [a.text.strip() for a in tag.find_all("a")]
                value = ", ".join(names) if names else tag.text.strip()

                if label == "作詞":
                    meta_info["lyricist"] = value
                elif label == "作曲":
                    meta_info["composer"] = value
                elif label == "編曲":
                    meta_info["arranger"] = value

                label = None

    return {
        "title": song_title,
        "release_date": meta_info["release_date"],
        "lyricist": meta_info["lyricist"],
        "composer": meta_info["composer"],
        "arranger": meta_info["arranger"],
        "lyrics": lyrics
    }

def get_first_two_song_links(artist_url):
    base_url = "https://utaten.com"
    response = requests.get(artist_url)
    soup = BeautifulSoup(response.text, "html.parser")

    song_tags = soup.select("p.searchResult__title h3 a")
    song_links = []
    for tag in song_tags[:2]:  # 最初の2曲のみ
        title = tag.text.strip()
        url = base_url + tag["href"]
        song_links.append((url, title))
    return song_links

# 実行
artist_url = "https://utaten.com/artist/lyric/32175"
songs = get_first_two_song_links(artist_url)

results = []
for url, title in songs:
    print(f"取得中: {title}")
    song_data = extract_song_info_from_page(url, title)
    results.append(song_data)
    time.sleep(1)  # サーバーに優しく

# CSV保存
df = pd.DataFrame(results)
df.to_csv("lyrics_2songs.csv", index=False, encoding="utf-8-sig")
print("最初の2曲をCSVに保存しました：lyrics_2songs.csv")
