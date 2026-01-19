import os
import queue
import sounddevice as sd
import json
import threading
from vosk import Model, KaldiRecognizer
from tkinter import Tk, Label
from PIL import Image, ImageTk
import time
import pyttsx3
import webbrowser
from groq import Groq  # Groqをインポート

# パラメータ
GROQ_API_KEY = os.environ.get("GROQ_API_KEY") 
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEYが設定されていません。環境変数にAPIキーを設定してください。")
running = True
navie_awake = False

# Groqクライアントの初期化
client = Groq(api_key=GROQ_API_KEY)

speech_queue = queue.Queue()

def speech_loop():
    # ✅ 重要な修正：エンジンの初期化をスレッド内部に移動
    # これにより、TTSエンジンがこのスレッド専用になり、競合を回避できる
    tts_engine = pyttsx3.init()
    tts_engine.setProperty('rate', 160)
    
    # 日本語音声の設定（システムにインストールされているかによる）
    voices = tts_engine.getProperty('voices')
    for v in voices:
        if "JP" in v.id or "Japan" in v.name:
            tts_engine.setProperty('voice', v.id)
            break

    while running:
        try:
            # タイムアウトを設定して、ループがrunning状態を確認できるようにする
            text = speech_queue.get(timeout=0.5) 
            
            if text:
                # print(f"音声再生中: {text}") # デバッグ用
                tts_engine.say(text)
                tts_engine.runAndWait()
                
        except queue.Empty:
            continue
        except Exception as e:
            print(f"音声再生エラー: {e}")
            # エラーが発生した場合、再初期化を試みる（オプション）
            try:
                tts_engine = pyttsx3.init()
            except:
                pass

speech_thread = threading.Thread(target=speech_loop, daemon=True)
speech_thread.start()

# Vosk日本語モデルの読み込み
model_path = "vosk-model-small-ja-0.22"
if not os.path.exists(model_path):
    raise FileNotFoundError("Vosk日本語モデルをダウンロードしてフォルダに入れてください")
model = Model(model_path)
recognizer = KaldiRecognizer(model, 16000)

# 音声録音設定
q = queue.Queue()

def audio_callback(indata, frames, time, status):
    if status:
        print(status)
    q.put(bytes(indata))

def show_image_popup():
    root = Tk() # Tkinterウィンドウの初期化
    root.overrideredirect(True)  # ウィンドウ枠を削除
    root.wm_attributes("-topmost", True)
    root.wm_attributes("-transparentcolor", "white")  # 白を透明色として設定（画像背景色による）

    # 画像の読み込み
    global original_img  # animate_speech() 用
    original_img = Image.open("navie.png").convert("RGBA")
    img_width, img_height = 200, 200

    # 画面サイズの取得
    screen_width = root.winfo_screenwidth()

    # 表示位置の計算（右上、画像幅を確保）
    x = screen_width - img_width - 10  # -10 は右側のマージン
    y = 10  # 上側のマージン

    # ウィンドウの位置とサイズを設定
    root.geometry(f"{img_width}x{img_height}+{x}+{y}")

    # 画像の表示
    combined = original_img.resize((img_width, img_height), Image.LANCZOS) # 画像リサイズ時のフィルタリングアルゴリズム
    photo = ImageTk.PhotoImage(combined) # PIL（Pillow）で処理した画像をTkinterで表示可能な形式に変換
    label = Label(root, image=photo, bg="white") # TkinterのUIコンポーネント（ウィジェット）、文字や画像を表示
    label.image = photo # photoの参照を保持する（Pythonのガベージコレクションによる画像非表示を防ぐため）
    label.pack()

    # アニメーションの追加
    def animate_speech():
        for _ in range(6):
            for size in [210, 200]:
                resized = original_img.resize((size, size), Image.LANCZOS)
                bg = Image.new("RGBA", resized.size, (255, 255, 255, 0))
                combined = Image.alpha_composite(bg, resized)
                new_img = ImageTk.PhotoImage(combined) 
                label.config(image=new_img)
                label.image = new_img
                time.sleep(0.2) 

    threading.Thread(target=animate_speech).start() # メインスレッドのブロックを避けるため、新しいスレッドを開始

    # 自動終了
    # root.after(5000, root.destroy)
    root.mainloop() # ウィンドウがすぐに消えないようにする




# 音声再生
def speak(text):
    print(f"ナビエ: {text}") # デバッグ用に表示
    speech_queue.put(text)

# ✅ 核となる修正：Groq AIを呼び出して応答を取得
def ask_ai(user_text):
    try:
        # 大賢者のキャラクター設定
        system_prompt = (
            "あなたはアニメ「転生したらスライムだった件」の「大賢者（ラファエル）」です。"
            "回答は常に冷静で、機械的かつ論理的に行ってください。"
            "回答の冒頭には必ず「告（こく）。」をつけてください。"
            "必要最低限の情報のみを簡潔に答えてください。"
            "日本語で答えてください。"
        )

        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.3, # 温度を低く設定し、回答をよりロボット/大賢者らしくする
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        print(f"AI Error: {e}")
        return "申し訳ありません。解析に失敗しました。"

# ✅ 音声コマンドプロセッサ
def handle_command(text):
    global navie_awake
    if not navie_awake:
        return

    print(f"User Command: {text}")

    # 1. 特定のハードコードされたコマンドを先に処理
    if "youtube" in text.lower() or "ユーチューブ" in text:
        speak("告。YouTubeへのアクセスを開始します。")
        webbrowser.open("https://www.youtube.com")
        return # 実行完了後はAIに問い合わせない
    
    elif "gmail" in text.lower() or "ジーメール" in text:
        speak("告。Gmailを開きます。")
        webbrowser.open("https://mail.google.com")
        return

    elif "終わり" in text or "さようなら" in text or "終了" in text:
        speak("告。スキル、ナビエを終了します。")
        navie_awake = False
        # ここでGUIを閉じるかどうか検討可能
        return

    # 2. その他の質問はすべてGroq AI（大賢者モード）に任せる
    # 雑音によるトリガーを避けるため、文字数が一定以上の長さの場合のみ問い合わせる
    if len(text) > 2: 
        ai_response = ask_ai(text)
        speak(ai_response)

# メインプログラム - リスニング開始
def start_listening():
    global running, navie_awake

    # GUIの起動は一度だけで良い、またはウェイクワードトリガー時に配置可能
    # ここでは簡単な処理を実演：
    # threading.Thread(target=show_image_popup, daemon=True).start()

    with sd.RawInputStream(samplerate=16000, blocksize=8000,
                           dtype='int16', channels=1, callback=audio_callback):
        print("ナビエは待機中...「ナビエ」と呼びかけてください。")
        while running:
            try:
                data = q.get(timeout=0.5)
                if recognizer.AcceptWaveform(data):
                    result = json.loads(recognizer.Result())
                    text = result.get("text", "").replace(" ", "") # 比較しやすいようにスペースを削除
                    
                    if not text:
                        continue

                    print("認識結果：", text)

                    if not navie_awake:
                        if is_wake_word(text):
                            navie_awake = True
                            print("ナビエ起動中！")
                            # 魔法陣GUIをトリガー
                            try:
                                threading.Thread(target=show_image_popup, daemon=True).start()
                            except:
                                pass # 重複起動によるエラーを防止
                            speak("告。ナビエ、起動しました。")
                    else:
                        # 既に起動済み、コマンドを処理
                        handle_command(text)

            except queue.Empty:
                continue

def is_wake_word(text):
    possible_variants = ["ナビエ", "ナビ", "ラファエル", "大賢者"]
    for variant in possible_variants:
        if variant in text:
            return True
    return False

if __name__ == "__main__":
    try:
        start_listening()
    except KeyboardInterrupt:
        print("\n[ナビエ] プログラムを終了しています...")
        running = False
        time.sleep(1)