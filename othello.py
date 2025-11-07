# coding: UTF-8
import tkinter
from tkinter import filedialog, messagebox
from copy import deepcopy
import re
from PIL import Image, ImageTk
import random
from datetime import datetime
from time import sleep

# ループのインターバル時間
REFRESH = 30


# --- オセロゲーム本体 ---
class Othello:
    def __init__(self):
        self.board = Board()
        # 盤面の初期化処理をBoardクラスに移動
        self.board.init_board_setup()
        # 盤面の状態をBoardクラスで一元管理する
        # self.board.coord_to_piece は init_board_setup で初期化される
        self.game_mode = None
        self.is_replay_mode = False

        self.view = TkView(self, self.board) # self.view.setup_and_run() でゲーム開始

        # プレイヤー先攻・後攻の辞書を定義する
        self.view.players = {}
        # ランダムプレーヤーのインスタンスを生成
        self.random = RandomPlayer(self.view)

    def update_game_state(self):
        """ゲームモードが選択された後に呼ばれる初期設定"""
        if self.board.finish_flag:
            if not self.board.result_write_flag:
                self.board.get_result(self.view)
            self.view.alert_finish(self.board)
            return
        
        self.board.finish_game()
        if self.board.finish_flag:  # ゲーム終了
            self.update_game_state() # 再帰呼び出しで終了処理へ
            return
        
        # 手番がまだの場合のみ、打てるマスを検索
        if not self.board.hit:
            self.view.clear_avalable_cells()
            self.search_avalable_cell()

            # 打てる手がない場合のパス処理
            if not self.board.search_hit_list_coord:
                self.board.pass_count += 1
                if self.board.pass_count >= 2:
                    self.board.finish_flag = True
                    print("手詰り")
                    self.update_game_state()  # 状態更新を呼び出す
                else:
                    player_type = self.view.players.get(self.board.turn)
                    if player_type == "human":
                        self.view.alert_pass_human(self.handle_pass)
                    else:
                        self.view.alert_pass_cpu(self.handle_pass)
                return
            
            # ターン表示の更新
        self.view.update_turn_display()

    def start_game_setup(self):
        """ゲーム開始時のセットアップ"""
        self.board.turn = "first"
        self.board.turn_start_time = datetime.now() # 最初のターンの開始時間を記録
        self.update_game_state()
        
    def handle_pass(self):
        """パスの処理"""
        self.board.change_turn()
        self.update_game_state()

    def handle_cpu_turn(self):
        """CPUのターン処理"""
        player_type = self.view.players.get(self.board.turn)
        if player_type in ["random", "random_2", "random_3"]:
            self.board.hit = True # CPUの思考中にループが再実行されるのを防ぐ
            
            # 思考中に見えるように少し遅延させる
            delay_ms = 1500
            if player_type == "random":
                self.view.cpu_turn_job_id = self.view.window.after(delay_ms, self.random_hit_1)
            elif player_type == "random_2":
                self.view.cpu_turn_job_id = self.view.window.after(delay_ms, self.random_hit_2)
            elif player_type == "random_3":
                self.view.cpu_turn_job_id = self.view.window.after(delay_ms, self.random_hit_3)
    
    def human_hit(self, coord):
        """人間のプレイヤーがマスをクリックしたときの処理"""
        if self.board.hit: # すでに処理中の場合は何もしない
            return

        # 駒が置けるマスか確認
        self.board.check_avalable_hit(coord, self.view)
        if self.board.avalable_hit:
            self.board.hit = True # 処理開始のフラグ
            
            #  UI更新
            self.view.clear_avalable_cells()
            self.view.delete_pass_button()
            if self.view.alert_flag:
                self.view.delete_alert()

            # ゲームロジック
            self.board.dohit(coord)
            log_entry = self.board.play_log[-1]
            self.view.update_log_display(log_entry)
            self.board.reverse_piece(coord, self.view)
            
            if self.board.turn == "first":
                self.view.draw_piece_black(coord)
            elif self.board.turn == "second":
                self.view.draw_piece_white(coord)
            
            self.board.pass_count = 0
            self.board.change_turn()
            
            # 次の状態を更新
            self.update_game_state()
        else:
            self.view.alert_message_human()
    
    def start_replay(self):
        """リプレイ機能を開始する"""
        self.is_replay_mode = True
        file_path = filedialog.askopenfilename(
            title="リプレイするログファイルを選択",
            filetypes=[("テキストファイル", "*.txt")]
        )
        
        if not file_path:
            self.view.restart_game() # ファイル選択がキャンセルされたらメニューに戻る
            return

        # モード選択ボタンなどを非表示にする
        self.view.mode_destory()
        # リプレイ用の操作UIを作成
        self.view.create_replay_controls()
        # 盤面を初期状態に戻す
        self.board.init_board_setup()
        self.view.redraw_board()

        move_tags = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    self.view.log_text.insert(tkinter.END, line)
                    # 正規表現で 'X_Y' 形式のタグを安全に抽出
                    match = re.search(r'が (\d{1,2}_\d{1,2}) に配置', line)
                    if match:
                        move_tags.append(match.group(1))
        except Exception as e:
            messagebox.showerror("エラー", f"ログファイルの読み込みに失敗しました: {e}")
            self.view.restart_game()
            return

        if not move_tags:
            messagebox.showinfo("情報", "ログファイルに着手情報が見つかりませんでした。")
            self.view.restart_game()
            return
        self.view.log_text.config(state=tkinter.DISABLED) # ログを編集不可に
        self.view.start_replay_moves(move_tags)

    # --- 打てるマス検索 ---
    def search_avalable_cell(self):
        # 初期化
        self.board.search_hit_list_coord = []
        self.board.search_hit_list_tag = []
        self.board.search_flag = True

        # 打てる手を保存したリストを生成(可視化用)
        self.random.search_hit(self.board)
        for tag in self.board.search_hit_list_tag:
            coord = self.view.tag_to_coord[tag]
            if self.board.coord_to_piece[coord] == 0:
                if coord not in self.board.search_hit_list_coord:
                    self.board.search_hit_list_coord.append(coord)
                    
        # 可視化
        for cell in self.board.search_hit_list_coord:
            self.view.draw_avalable_cell(cell)
                        
    # --- 打てるマス検索(コンピューター用) ---
    def random_avalable_cell(self):
        # 初期化
        self.board.random_hit_list_coord = []
        self.board.random_hit_list_tag = []

        # 打てる手を保存したリストを生成
        self.random.random_hit(self.board)
        for tag in self.board.random_hit_list_tag:
            coord = self.view.tag_to_coord[tag]
            if self.board.coord_to_piece[coord] == 0:
                if coord not in self.board.random_hit_list_coord:
                    self.board.random_hit_list_coord.append(coord)
                    
    # --- コンピューター用(共通処理) ---
    def cpu_hit_base(self, strategy_func):
        self.view.alert_message_random()    
        self.random_avalable_cell()

        hit_count = len(self.board.random_hit_list_coord)

        if hit_count == 0:
            # パス処理はupdate_game_stateに任せる
            self.board.change_turn()
            self.update_game_state()
            return

        self.board.pass_count = 0
        coord = strategy_func(hit_count)
        self.common_hit(coord)
        self.update_game_state()

    # --- コンピューター用(完全乱数) ---
    def random_hit_1(self):
        def strategy(hit_count):
            if hit_count == 1:
                idx = 0
            else:
                idx = random.randint(0, hit_count - 1)
            return self.board.random_hit_list_coord[idx]
        self.cpu_hit_base(strategy)

    # --- コンピューター用(少し強い) ---
    def random_hit_2(self):
       
        def strategy(hit_count):
            temp_hit_list = list(self.board.random_hit_list_coord)
            
            # 角を取れるなら最優先
            for coord in temp_hit_list:
                tag = self.view.coord_to_tag[coord]
                if tag in ["0_0", "0_7", "7_0", "7_7"]:
                    return coord

            # 角の隣は避ける
            avoid_list = []
            for x in range(0, 8, 7):
                for y in range(0, 8, 7):
                    for dx in range(-1, 2, 1):
                        for dy in range(-1, 2, 1):
                            if dx == 0 and dy == 0: continue
                            avoid_tag = f"{x+dx}_{y+dy}"
                            if self.view.tag_to_coord.get(avoid_tag):
                                avoid_list.append(self.view.tag_to_coord[avoid_tag])
            
            preferred_list = [c for c in temp_hit_list if c not in avoid_list]

            if not preferred_list: # 避けた結果、手が無くなったら元のリストから選ぶ
                preferred_list = temp_hit_list

            return random.choice(preferred_list)
        self.cpu_hit_base(strategy) 
    
    # --- コンピューター用(強い) ---
    def random_hit_3(self):
        def strategy(hit_count):
            temp_hit_list = list(self.board.random_hit_list_coord)

            # 角を取れるなら最優先
            for coord in temp_hit_list:
                tag = self.view.coord_to_tag[coord]
                if tag in ["0_0", "0_7", "7_0", "7_7"]:
                    return coord

            # 評価値が最も高い手を選ぶ
            max_eval_coord = None
            max_eval_score = -float('inf')
            for coord in temp_hit_list:
                tag = self.view.coord_to_tag[coord]
                eval_value = self.board.tag_to_evalvalue[tag]
                if eval_value > max_eval_score:
                    max_eval_score = eval_value
                    max_eval_coord = coord
            return max_eval_coord
        self.cpu_hit_base(strategy)
        
    # --- random_hit共通処理 ---
    def common_hit(self, coord, from_replay=False):
        # UI更新
        self.view.clear_avalable_cells()
        # アラートがあればを削除
        if self.view.alert_flag:
            self.view.delete_alert()

        # ゲームロジック (リプレイ中はログ追加をスキップ)
        self.board.dohit(coord)
        if not from_replay:
            log_entry = self.board.play_log[-1]
            self.view.update_log_display(log_entry)
        self.board.reverse_piece(coord, self.view)

        if self.board.turn == "first":
            self.view.draw_piece_black(coord)
        elif self.board.turn == "second":
            self.view.draw_piece_white(coord)
        
        # ターン変更
        self.board.change_turn()

        
# --- オセロ盤面作成 ---
class TkView:
    def __init__(self, othello, board):
        self.othello = othello
        self.board = board

        # ウィンドウサイズ、セルサイズ、ウィンドウからのオフセット指定
        self.WINDOW_SIZE = 590
        self.CELL_SIZE = 70
        self.BOARD_OFFSET = 15

        # アラート表示用の変数
        self.set_flag = False
        self.alert_flag = False
        self.restart_flag = False
        self.restart_flag_alert = False
        self.human_pass_button = None # 人間用パスボタンのウィジェットを保持
        self.replay_board_history = [] # リプレイ用の盤面状態履歴
        
        # 画像を保持するためのインスタンス変数
        self.black_piece_img = None
        self.white_piece_img = None
        self.player_info = None
        self.replay_speed = 1000 # リプレイの再生速度 (ms)
        self.is_replay_paused = False # リプレイが一時停止中かどうかのフラグ
        self.pause_button = None
        self.replay_controls = [] # リプレイ用のUI要素を保持するリスト
        self.update_loop_id = None # afterのジョブIDを保持
        self.cpu_turn_job_id = None # CPU思考処理のafterジョブID
        self.replay_job_id = None # リプレイ再生のafterジョブID
        self.avalable_cell_tags = []

    def setup_and_run(self):
        """ウィンドウの初期化とメインループの開始"""
        self.init_window()
        self.choice_attack()
        self.update_loop() # 定期実行ループを開始
        self.window.mainloop()

    def update_loop(self):
        """定期的にゲームの状態をチェックし、CPUのターンなどを処理する"""
        if self.board.turn != "wait" and not self.board.hit:
            player_type = self.players.get(self.board.turn)
            if player_type != "human":
                self.othello.handle_cpu_turn()
        
        self.update_loop_id = self.window.after(500, self.update_loop)

    def load_images(self): # 画像(コマ)の読み込み
        """コマの画像を読み込み、リサイズしてPhotoImageオブジェクトを作成する"""
        try:
            # 画像ファイルを開き、セルのサイズに合わせてリサイズ
            black_img = Image.open("black.png").resize((self.CELL_SIZE, self.CELL_SIZE), Image.Resampling.LANCZOS)
            white_img = Image.open("white.png").resize((self.CELL_SIZE, self.CELL_SIZE), Image.Resampling.LANCZOS)
            self.black_piece_img = ImageTk.PhotoImage(black_img)
            self.white_piece_img = ImageTk.PhotoImage(white_img)
        except FileNotFoundError:
            messagebox.showinfo("情報", "コマの画像ファイル (black.png, white.png) が見つかりませんでした。\nデフォルトの描画でゲームを開始します。")
            self.black_piece_img = None
            self.white_piece_img = None

    def init_window(self):
        # ログ表示用ウィジェット
        self.log_text = None
        self.window = tkinter.Tk()
        self.window.title("Othello")
        self.window.resizable(width=True, height=False) # 横幅のサイズ変更を許可
        self.window.attributes("-topmost", True) # 常に最前面に表示
        # Escキーで終了する
        self.window.bind('<Escape>', self.on_escape_key)

        # コマ画像をロード
        self.load_images()
        
        # --- レイアウト用のフレームを作成 ---
        # 上部フレーム (キャンバスとログ用)
        top_frame = tkinter.Frame(self.window)
        top_frame.pack(side=tkinter.TOP)

        # 下部フレーム (情報表示用)
        self.info_frame = tkinter.Frame(self.window, height=100, bg='#008080')
        self.info_frame.pack(fill=tkinter.X, side=tkinter.BOTTOM)

        # コンストラクタによりセットされた情報からキャンバスを作成
        self.canvas = tkinter.Canvas(
            top_frame, # 親ウィジェットをtop_frameに修正
            width=self.WINDOW_SIZE,
            height=self.WINDOW_SIZE
        )

        # キャンバス内に正方形を点描
        self.canvas.create_rectangle(
            0, 0, self.WINDOW_SIZE, self.WINDOW_SIZE, fill="green")
        # cellのtagを保存するリスト生成(1_2, 3_5など)
        self.cells_tag = []
        # tagがキー、座標がバリューの辞書定義
        self.tag_to_coord = {}
        # 座標がキー、tagがバリューの辞書定義
        self.coord_to_tag = {}
        # クリックされたtag保存変数
        self.clicked_tag = "null"

        # 座標保持用の変数(x軸用)
        i = 0
        for h in range(
                self.BOARD_OFFSET,
                self.WINDOW_SIZE -
                self.BOARD_OFFSET,
                self.CELL_SIZE):

            # 座標保持用の変数(y軸用)
            j = 0
            for v in range(
                    self.BOARD_OFFSET,
                    self.WINDOW_SIZE -
                    self.BOARD_OFFSET,
                    self.CELL_SIZE):

                tag = "{}_{}".format(i, j)

                # x,y座標とセルサイズ指定により、オセロ盤を点描
                coord = (h, v, h + self.CELL_SIZE, v + self.CELL_SIZE)
                self.canvas.create_rectangle(*coord, fill="green", tags=tag)

                # リスト、辞書に情報を追加
                self.cells_tag.append(tag)
                self.tag_to_coord[tag] = coord
                self.coord_to_tag[coord] = tag

                # Boardから初期駒の状態を取得して描画
                piece = self.board.coord_to_piece.get(coord)
                if piece == 1:
                    self.draw_piece_black(coord)
                elif piece == 2:
                    self.draw_piece_white(coord)
                # 0の場合は何もしない

                # 以下のコードはBoardクラスで管理するため不要
                # if (j, i) in [(3, 3), (4, 4)]:
                # elif (j, i) in [(3, 4), (4, 3)]:
                # else: self.coord_to_piece[coord] = 0

                # tagのｙ座標成分に+1
                j += 1

            # tagのx軸成分に+1
            i += 1

        self.canvas.pack(side=tkinter.LEFT) # 左側に配置

        # セルクリック時のイベント設定
        self.canvas.bind("<ButtonPress-1>", self.handle_click)

        # ログ表示エリアの作成
        log_frame = tkinter.Frame(top_frame) # 親をtop_frameに変更
        log_frame.pack(side=tkinter.LEFT, fill=tkinter.BOTH, expand=True, padx=5) # 変更: fillとexpandを追加
        log_label = tkinter.Label(log_frame, text="プレイログ")
        log_label.pack(pady=5)
        self.log_text = tkinter.Text(log_frame, width=30, height=40) # widthを30に増加
        self.log_text.pack(fill=tkinter.BOTH, expand=True) # 変更: fillとexpandを追加

        # ログ用のタグを設定
        self.log_text.tag_config("black_player", foreground="white", background="black")
        self.log_text.tag_config("white_player", foreground="black", background="white")

        # リプレイ用のハイライトタグ
        self.log_text.tag_config("highlight", background="yellow", foreground="black")

        # ログ保存ボタンの作成
        self.save_log_button = tkinter.Button(log_frame, text="ログを保存", command=self.save_log_to_file)
        self.save_log_button.pack(pady=5, fill=tkinter.X)

    def on_escape_key(self, event=None):
        """Escキーが押されたときにウィンドウを閉じる"""
        self.window.destroy()

    def handle_click(self, event):
        if self.players.get(self.board.turn) == "human":
            self.on_cell_click(event)
            if self.clicked_tag != "null":
                coord = self.tag_to_coord.get(self.clicked_tag)
                if coord:
                    self.othello.human_hit(coord)
                self.clicked_tag = "null"

    def on_cell_click(self, event):
        item_id = self.canvas.find_closest(event.x, event.y)
        if not item_id: return
        tags = self.canvas.gettags(item_id[0])
        if tags:
            for tag in tags:
                if '_' in tag and 'piece' not in tag and 'arc' not in tag:
                    self.clicked_tag = tag
                    return
        self.clicked_tag = "null"
    
    def redraw_board(self):
        """現在の board.coord_to_piece に基づいて盤面全体を再描画する"""
        self.canvas.delete("all") # 一旦すべて消去
        self.init_board_display() # 盤の格子などを再描画
        for coord, piece in self.board.coord_to_piece.items():
            if piece == 1:
                self.draw_piece_black(coord)
            elif piece == 2:
                self.draw_piece_white(coord)
                    
    # --- ゲームモードの選択 ---
    def choice_attack(self):
        # モード選択ボタン配置
        self.describe = tkinter.Label(self.info_frame, text='Mode', bg='#008080', fg='#000000', width=10)
        self.describe.place(x=20, y=10)

        # mode_1 (human vs human)
        self.mode_1_button = tkinter.Button(self.info_frame, text='ヒト vs ひと', bg='#008080', fg='#000000', width=20,
                                            command=self.mode_1_clicked)
        self.mode_1_button.place(x=20, y=30)

        # mode_2(human vs random)
        self.mode_2_button = tkinter.Button(self.info_frame, text='ひと vs CPU', bg='#008080', fg='#000000', width=20,
                                            command=self.mode_2_clicked)
        self.mode_2_button.place(x=200, y=30)

        # mode_3(random vs random)
        self.mode_3_button = tkinter.Button(self.info_frame, text='CPU vs CPU', bg='#008080', fg='#000000', width=20,
                                            command=self.mode_3_clicked)
        self.mode_3_button.place(x=380, y=30)
        
        # mode_4 (Replay)
        self.mode_4_button = tkinter.Button(self.info_frame, text='リプレイ', bg='#008080', fg='#000000', width=20,
                                            command=self.othello.start_replay)
        self.mode_4_button.place(x=560, y=30)

    # --- リプレイ用の操作UIを作成 ---
    def create_replay_controls(self):
        self.replay_controls.clear()
        self.destroy_replay_controls()
        speed_frame = tkinter.Frame(self.info_frame, bg='#008080')
        speed_frame.place(x=20, y=10)

        speed_label = tkinter.Label(speed_frame, text='再生速度', bg='#008080', fg='#FFFFFF')
        speed_label.pack()
    
        # 速度変更ボタン
        speeds = [("x1", 1000), ("x2", 500), ("x4", 250)]
        for text, speed in speeds:
            btn = tkinter.Button(speed_frame, text=text, command=lambda s=speed: self.set_replay_speed(s))
            btn.pack(side=tkinter.LEFT, padx=2)
            self.replay_controls.append(btn)

        # 一時停止/再開ボタン
        self.pause_button = tkinter.Button(self.info_frame, text='一時停止', command=self.toggle_replay_pause)
        self.pause_button.place(x=120, y=30)

        # 一手戻る/進むボタン
        back_button = tkinter.Button(self.info_frame, text='<<', command=self.backward_replay)
        back_button.place(x=200, y=30)
        forward_button = tkinter.Button(self.info_frame, text='>>', command=self.forward_replay)
        forward_button.place(x=240, y=30)
        self.replay_controls.extend([back_button, forward_button])
        self.replay_controls.extend([speed_frame, speed_label])

    def destroy_replay_controls(self):
        for widget in self.replay_controls:
            widget.destroy()
        self.replay_controls.clear()

    # mode_1クリック時(human vs human)
    def mode_1_clicked(self):
        # モード選択ボタンを削除
        self.mode_destory()

        self.players["first"] = "human"
        self.players["second"] = "human"
        
        self.othello.start_game_setup()    

    # リプレイの再生速度を設定
    def set_replay_speed(self, speed_ms):
        self.replay_speed = speed_ms

    # リプレイの一時停止/再開を切り替える
    def toggle_replay_pause(self):
        self.is_replay_paused = not self.is_replay_paused
        if self.is_replay_paused:
            self.pause_button.config(text="再開")
        else:
            
            self.pause_button.config(text="一時停止")
            self.replay_move()

    # リプレイを一手進める
    def forward_replay(self):
        if not self.is_replay_paused:
            self.toggle_replay_pause()
        self.replay_move(manual_step=True)

    # リプレイを一手戻す
    def backward_replay(self):
        if not self.is_replay_paused:
            self.toggle_replay_pause()

        if self.replay_index > 0:
            self.replay_index -= 1
            prev_board_state = self.replay_board_history[self.replay_index]
            # 盤面状態を復元
            self.board.coord_to_piece = prev_board_state.copy()
            
            # ターンを正しく戻す
            if self.replay_index % 2 == 0:
                self.board.turn = "first"
            else:
                self.board.turn = "second"

            self.redraw_board()
            self.update_turn_display()
            self.highlight_log_line()
        
    def start_replay_moves(self, move_tags):
        self.replay_move_tags = move_tags
        self.replay_index = 0
        self.board.play_log.clear() # リプレイ開始時にログをクリア
        self.board.turn = "first"
        self.replay_board_history.clear()
        self.is_replay_paused = False
        self.replay_board_history.append(self.board.coord_to_piece.copy()) # 初期盤面を保存
        self.replay_move()
    
    def replay_move(self, manual_step=False):
        if self.is_replay_paused and not manual_step:
            return

        if self.replay_index < len(self.replay_move_tags):
            self.highlight_log_line()

            tag = self.replay_move_tags[self.replay_index]
            coord = self.tag_to_coord.get(tag)
            if coord:
                self.othello.common_hit(coord, from_replay=True)
                self.replay_index += 1
                self.replay_board_history.append(deepcopy(self.board.coord_to_piece))
                
            if not manual_step:
                self.replay_job_id = self.window.after(self.replay_speed, self.replay_move)
        else:
            self.highlight_log_line() # 最後の行をハイライト
            self.show_return_to_menu_button()
    
    def highlight_log_line(self):
        """ログの指定された行をハイライトする"""
        self.log_text.tag_remove("highlight", "1.0", tkinter.END)
        if self.replay_index < len(self.replay_move_tags):
            # ログは1から始まるので +1
            line_to_highlight = self.replay_index + 1
            start_index = f"{line_to_highlight}.0"
            end_index = f"{line_to_highlight}.end"
            self.log_text.tag_add("highlight", start_index, end_index)
            self.log_text.see(start_index)

    # mode_2クリック時(human vs random)
    def mode_2_clicked(self):
        # モード選択ボタン削除
        self.mode_destory()
        #  (先攻ボックス)
        self.before_button = tkinter.Button(self.info_frame, text='先手:黒', bg='#008080', fg='#000000',
                                            width=20, command=self.before_clicked)
        self.before_button.place(x=20, y=20)
        #  (後攻ボックス)
        self.after_button = tkinter.Button(self.info_frame, text='後手:白', bg='#008080', fg='#000000',
                                           width=20, command=self.after_clicked)
        self.after_button.place(x=200, y=20)

    # mode_3クリック時(randmo vs random)
    def mode_3_clicked(self):
        # モード選択ボタンを削除
        self.mode_destory()
        self.describe = tkinter.Label(self.info_frame, text='先手のレベルを選択', bg='#008080', fg='#000000',
                                      width=25)
        self.describe.place(x=20, y=10)

        #  (先攻ボックス)
        self.before_computer_1 = tkinter.Button(self.info_frame, text='弱いかも…', bg='#008080', fg='#000000', width=20,
                                                command=lambda: self.before_computer_clicked(0))
        self.before_computer_1.place(x=20, y=30)
        self.before_computer_2 = tkinter.Button(self.info_frame, text='ちょっと強い？', bg='#008080', fg='#000000', width=20,
                                                command=lambda: self.before_computer_clicked(1))
        self.before_computer_2.place(x=200, y=30)
        self.before_computer_3 = tkinter.Button(self.info_frame, text='さらに強いのかなぁ…', bg='#008080', fg='#000000', width=20,
                                                command=lambda: self.before_computer_clicked(2))
        self.before_computer_3.place(x=380, y=30)

    # モード選択ボタン削除
    def mode_destory(self):
        self.mode_1_button.destroy()
        self.mode_2_button.destroy()
        self.mode_3_button.destroy()
        self.mode_4_button.destroy() # mode_4_buttonも削除
        self.describe.destroy()

    # 先攻ボタンクリック時(human vs random)
    def before_clicked(self):
        # ボタンクリック後、ボタンを削除
        self.before_button.destroy()
        self.after_button.destroy()
        self.players["first"] = "human"
        self.after_computer()

    # 後攻ボタンクリック時(human vs random)
    def after_clicked(self):
        # ボタンクリック後、ボタンを削除
        self.before_button.destroy()
        self.after_button.destroy()
        self.players["second"] = "human"
        self.before_computer()

    # 後攻ボタンクリック時(human vs random)
    def before_computer(self):
        if hasattr(self, 'describe'): self.describe.destroy()
        
        self.describe = tkinter.Label(self.info_frame, text='先手のレベルを選択', bg='#008080', fg='#000000',
                                      width=25)
        self.describe.place(x=20, y=10)

        # (後攻ボックス)
        self.before_computer_1 = tkinter.Button(self.info_frame, text='弱いかも…', bg='#008080', fg='#000000', width=20,
                                                command=lambda: self.before_computer_clicked_human(0))
        self.before_computer_1.place(x=20, y=30)
        self.before_computer_2 = tkinter.Button(self.info_frame, text='ちょっと強い？', bg='#008080', fg='#000000', width=20,
                                                command=lambda: self.before_computer_clicked_human(1))
        self.before_computer_2.place(x=200, y=30)
        self.before_computer_3 = tkinter.Button(self.info_frame, text='さらに強いのかなぁ…', bg='#008080', fg='#000000', width=20,
                                                command=lambda: self.before_computer_clicked_human(2))
        self.before_computer_3.place(x=380, y=30)

    # 後攻ボタンクリック時(human vs random)
    def before_computer_clicked_human(self, id_num):
        
        self.players["first"] = ["random", "random_2", "random_3"][id_num]
        self.before_computer_1.destroy()
        self.before_computer_2.destroy()
        self.before_computer_3.destroy()
        self.describe.destroy()

        # コンピューターの選択(先攻) tkinterのcommandの特質より関数をネストして使用
        self.othello.start_game_setup()
        
    # コンピューターの選択(先攻)
    def before_computer_clicked(self, id_num):
        if id_num == 0:
            self.players["first"] = "random"

        elif id_num == 1:
            self.players["first"] = "random_2"

        elif id_num == 2:
            self.players["first"] = "random_3"

        self.before_computer_1.destroy()
        self.before_computer_2.destroy()
        self.before_computer_3.destroy()
        self.after_computer()

    def after_computer(self):
        if hasattr(self, 'describe'): self.describe.destroy()
        self.describe = tkinter.Label(self.info_frame, text='後手のレベルを選択', bg='#008080', fg='#000000',
                                      width=25)
        self.describe.place(x=20, y=10)

        # (後攻ボックス)
        self.after_computer_1 = tkinter.Button(self.info_frame, text='弱いかも…', bg='#008080', fg='#000000', width=20,
                                               command=lambda: self.after_computer_clicked(0))
        self.after_computer_1.place(x=20, y=30)
        self.after_computer_2 = tkinter.Button(self.info_frame, text='ちょっと強い？', bg='#008080', fg='#000000', width=20,
                                               command=lambda: self.after_computer_clicked(1))
        self.after_computer_2.place(x=200, y=30)
        self.after_computer_3 = tkinter.Button(self.info_frame, text='さらに強いのかなぁ…', bg='#008080', fg='#000000', width=20,
                                               command=lambda: self.after_computer_clicked(2))
        self.after_computer_3.place(x=380, y=30)

    # コンピューターの選択(後攻)
    def after_computer_clicked(self, id_num):
        if id_num == 0:
            self.players["second"] = "random"

        elif id_num == 1:
            self.players["second"] = "random_2"

        elif id_num == 2:
            self.players["second"] = "random_3"

        self.after_computer_1.destroy()
        self.after_computer_2.destroy()
        self.after_computer_3.destroy()
        self.describe.destroy()
        self.othello.start_game_setup()

    # 駒が打たれた時の駒の点描(先攻の場合)
    def draw_piece_black(self, coord):
        self._draw_piece(coord, self.black_piece_img, "black")

    # 駒が打たれた時の駒の点描(先攻の場合)
    def draw_piece_white(self, coord):
        self._draw_piece(coord, self.white_piece_img, "white")
        
    def _draw_piece(self, coord, img, color):
        cell_tag = self.coord_to_tag[coord]
        piece_tag = cell_tag + "_piece"
        self.canvas.delete(piece_tag)

        if img:
            x = coord[0] + self.CELL_SIZE / 2
            y = coord[1] + self.CELL_SIZE / 2
            self.canvas.create_image(x, y, image=img, tags=(cell_tag, piece_tag))
        else:
            # 画像がない場合は円を描画
            offset = 5 # 円を少し小さくするためのオフセット
            self.canvas.create_oval(coord[0] + offset, coord[1] + offset, coord[2] - offset, coord[3] - offset, fill=color, outline=color, tags=(cell_tag, piece_tag))

    # 置けるマスの可視化
    def draw_avalable_cell(self, coord):
        # ターンに応じて円の色を決定
        player_type = self.players.get(self.board.turn)
        color = "yellow"  # デフォルトの色（CPU対戦など）
        if player_type == "human":
            if self.board.turn == "first":
                color = "yellow"  # 先攻（黒）のターンは黄色
            elif self.board.turn == "second":
                color = "skyblue2"  # 後攻（白）のターンはスカイブルー

        tag = self.coord_to_tag[coord]
        tag = tag + "_arc"
        self.canvas.create_oval(*coord, outline=color, width=2, tags=tag)
        self.avalable_cell_tags.append(tag)

    def show_return_to_menu_button(self):
        """モード選択に戻るボタンを表示する"""
        if hasattr(self, 'return_button') and self.return_button.winfo_exists():
            return # 既に表示されている場合は何もしない
        self.return_button = tkinter.Button(self.info_frame, text='モード選択に戻る', command=self.restart_game)
        self.return_button.place(x=350, y=30)
        self.replay_controls.append(self.return_button)

    def init_board_display(self):
        """盤面の格子線などを描画する"""
        self.canvas.create_rectangle(0, 0, self.WINDOW_SIZE, self.WINDOW_SIZE, fill="green")
        for i in range(8):
            for j in range(8):
                tag = f"{i}_{j}"
                coord = self.tag_to_coord[tag]
                self.canvas.create_rectangle(*coord, fill="green", tags=tag)
        
    # 可視化削除メソッド
    def clear_avalable_cells(self):
        for tag in self.avalable_cell_tags:
            self.canvas.delete(tag)
        self.avalable_cell_tags.clear()

    # 置けない所がクリックされた場合(human plyaer)
    def alert_message_human(self):
        # アラートが表示されていなければ
        if not self.alert_flag:
            self.alert = tkinter.Label(self.info_frame, text="ここには置けません", bg='#008080', fg='#000000', width=20)
            self.alert.place(x=300, y=20)

            self.alert_flag = True

    # 試行中のアラート(random plyaer)
    def alert_message_random(self):
        # アラートが表示されていなければ
        if not self.alert_flag:
            self.alert = tkinter.Label(self.info_frame, text='Thinking', bg='#008080', fg='#000000', width=20)
            self.alert.place(x=300, y=20)

            self.alert_flag = True
                
    # パスボタン表示 (人間用)
    def alert_pass_human(self, pass_callback):
        # ボタンがまだ表示されていなければ作成
        if not self.human_pass_button:
            self.human_pass_button = tkinter.Button(self.info_frame, text='打てる手がないためパス', bg='#FFA500', fg='#000000',
                                                    width=20, command=lambda: self.execute_pass(pass_callback))
            self.human_pass_button.place(x=200, y=30)

    # 人間用パスボタンの削除
    def delete_pass_button(self):
        if self.human_pass_button:
            self.human_pass_button.destroy()
            self.human_pass_button = None

    # 人間用パス実行
    def execute_pass(self, pass_callback):
        self.delete_pass_button() # ボタンを削除
        pass_callback() # Boardのchange_turnを呼び出す
  
    # パスボタン表示 (CPU用)
    def alert_pass_cpu(self, pass_callback):
        # ボタンがまだ表示されていなければ作成
        if not self.human_pass_button:
            turn_str = "黒(先)" if self.board.turn == "first" else "白(後)"
            self.human_pass_button = tkinter.Button(
                self.info_frame, 
                text=f'CPU({turn_str})はパスしました (OK)', 
                bg='#FFA500', fg='#000000',
                width=30, 
                command=lambda: self.execute_pass(pass_callback))
            self.human_pass_button.place(x=200, y=30)

    # パスアラート(random player)
    def alert_pass(self):
        if self.pass_flag_alert == False:
            self.alert_pass_button = tkinter.Button(self.info_frame, text='Pass your turn', bg='#008080', fg='#000000',
                                                    width=20, command=self.turn_pass)
            self.pass_flag_alert = True
        self.alert_pass_button.place(x=200, y=50)
        # アラート表示に変更
        self.alert_flag = True

    # パス実行
    def turn_pass(self):
        self.alert_pass_button.destroy()
        self.alert_flag = False
        self.pass_flag_alert = False
        # ターン変更
        self.board.change_turn()

    # アラート削除メソッド
    def delete_alert(self):
        if hasattr(self, 'alert'):
            self.alert.destroy()
        self.alert_flag = False

    # ゲーム終了アラート
    def alert_finish(self, board):        
        if hasattr(self, "player_info"): self.player_info.destroy()
        black_count, white_count = board.result_count        
        self.alert = tkinter.Label(self.info_frame, text='ゲーム終了', bg='#008080', fg='#000000', width=40)
        if not self.restart_flag_alert:
            self.alert_restart = tkinter.Button(self.info_frame, text='再びゲーム', bg="#FFFB00", fg='#000000',
                                                width=20, command=self.restart_game)
            self.restart_flag_alert = True
        
        self.result = tkinter.Label(self.info_frame, text=f'先手 (黒): {black_count}\n後手 (白): {white_count}', 
                                    bg='#008080', fg='#000000', width=40)
        self.alert.place(x=250, y=20)
        self.alert_restart.place(x=20, y=20)
        self.result.place(x=250, y=20)
    
    # 再びゲームをする
    def restart_game(self):
        # afterで予約されたupdate_loopをキャンセルする
        if hasattr(self, 'update_loop_id'):
            self.window.after_cancel(self.update_loop_id)
        # CPUの思考処理がスケジュールされていればキャンセルする
        if hasattr(self, 'cpu_turn_job_id') and self.cpu_turn_job_id:
            self.window.after_cancel(self.cpu_turn_job_id)
        # リプレイ再生処理がスケジュールされていればキャンセルする
        if hasattr(self, 'replay_job_id') and self.replay_job_id:
            self.window.after_cancel(self.replay_job_id)

        self.restart_flag = True
        self.log_text.config(state=tkinter.NORMAL) # ログを編集可能に戻す
        self.window.destroy()
        self.othello.is_replay_mode = False
        play_othello()

    # ログ表示を更新する
    def update_log_display(self, log_entry):
        turn_count, turn, coord = log_entry
        tag = self.coord_to_tag[coord]
        
        self.log_text.insert(tkinter.END, f"{turn_count}: ")
        self.log_text.insert(tkinter.END, "黒(先)" if turn == "first" else "白(後)", "black_player" if turn == "first" else "white_player")        
        self.log_text.insert(tkinter.END, f"が {tag} に配置\n")
        self.log_text.see(tkinter.END)

    def update_turn_display(self):
        if self.set_flag:
            self.player_info.destroy()
            self.set_flag = False
        
        player_type = self.players.get(self.board.turn)
        if not player_type: return

        turn_str = " (黒)" if self.board.turn == "first" else " (白)"
        text = ""
        if player_type == "human":
            text = f'ヒトのターン: {turn_str}'
        elif player_type == "random":
            text = f'Turn of CPU(weak): {turn_str}'
        elif player_type == "random_2":
            text = f'Turn of CPU(little strong): {turn_str}'
        elif player_type == "random_3":
            text = f'Turn of CPU(strong): {turn_str}'
        
        if text:
            self.player_info = tkinter.Label(self.info_frame, text=text, bg='#008080', fg='#000000', width=30)
            self.player_info.place(x=20, y=20)
            self.set_flag = True
    
    # ログをファイルに保存する
    def save_log_to_file(self):
        # ファイル保存ダイアログを開く
        file_path = filedialog.asksaveasfilename(
            title="ログを保存",
            filetypes=[("テキストファイル", "*.txt")],
            defaultextension="txt",
            initialfile=f"othello_log_{datetime.now():%Y%m%d_%H%M%S}.txt"
        )

        # ファイルパスが選択された場合（キャンセルされなかった場合）
        if file_path:
            # Textウィジェットから内容を取得
            log_content = self.log_text.get("1.0", tkinter.END)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(log_content)


# --- ゲームプレイヤーのクラスを定義する ---
class Player:
    def __init__(self, *args, **kargs): pass

    def __str__(self): return "suoer player"

    def play(self, board): pass


# --- 人間のプレイヤー ---
class HumanPlayer(Player):
    def __init__(self, view):
        self.view = view


# --- コンピューターのプレイヤー ---
class RandomPlayer:
    """コンピューターの手や、人間が打てる場所を探す役割を担うクラス"""
    def __init__(self, view):
        self.view = view

    def random_hit(self, board):
        """コンピュータが打てるすべての空きマスをチェックし、打てる場合はboardのリストに追加する"""
        for x in range(8):
            for y in range(8):
                tag = f"{x}_{y}"
                coord = self.view.tag_to_coord[tag]
                if board.coord_to_piece[coord] == 0:
                    board.check_random_hit(coord, self.view)

    # ひっくり返せる手を保存
    def search_hit(self, board):  
        """人間プレイヤーのために、打てるすべての空きマスをチェックし、打てる場合はboardのリストに追加する（可視化用）"""
        for x in range(8):
            for y in range(8):
                tag = f"{x}_{y}"
                coord = self.view.tag_to_coord[tag]
                if board.coord_to_piece[coord] == 0:
                    board.check_search_hit(coord, self.view)


# --- 盤面情報,ゲーム情報管理クラス ---
class Board: 
    def __init__(self):
        # ターン管理変数(first:先攻, second:後攻 wait:ゲーム前)
        self.turn = "wait"
        # ターン数カウント変数
        self.count = 0
        # プレイログ
        self.play_log = []
        # 手を打ったかの変数
        self.hit = False
        # 置けるマスか判断
        self.avalable_hit = False
        # ひっくり返す時の終点を保存する辞書定義
        self.reverse_dic = {}

        # 先攻：1 後攻:2の辞書定義
        self.turn_to_piece = {}
        self.turn_to_piece["first"] = 1
        self.turn_to_piece["second"] = 2

        # ランダムに打つ時の打てる手リスト
        self.random_hit_list_tag = []
        self.random_hit_list_coord = []

        # 可視化用に打つ時の打てる手リスト
        self.search_hit_list_tag = []
        self.search_hit_list_coord = []

        # お互い打つ手がなくなった時にゲーム終了する
        self.pass_count = 0 # 連続パス回数
        # ゲームを終了フラグ
        self.finish_flag = False
        # ゲーム結果格納リスト
        self.result_count = []
        # 再びゲーム開始ボタンフラグ
        self.restart_flag = False
        # 可視化しているか確認フラグ
        self.search_flag = False
        # 結果書き込み済みフラグ
        self.result_write_flag = False
        # 評価表の辞書
        self.tag_to_evalvalue = {}
        # --- 統計情報 ---
        self.turn_start_time = None # 手番開始時刻
        self.turn_times = {"first": [], "second": []} # 手番ごとの思考時間
        self.max_reversals = {"first": 0, "second": 0} # 最大反転数

        self.tag_to_evalvalue["0_0"] = 30
        self.tag_to_evalvalue["0_1"] = -12
        self.tag_to_evalvalue["0_2"] = 0
        self.tag_to_evalvalue["0_3"] = -1
        self.tag_to_evalvalue["0_4"] = -1
        self.tag_to_evalvalue["0_5"] = 0
        self.tag_to_evalvalue["0_6"] = -12
        self.tag_to_evalvalue["0_7"] = 30
        self.tag_to_evalvalue["1_0"] = -12
        self.tag_to_evalvalue["1_1"] = -15
        self.tag_to_evalvalue["1_2"] = -3
        self.tag_to_evalvalue["1_3"] = -3
        self.tag_to_evalvalue["1_4"] = -3
        self.tag_to_evalvalue["1_5"] = -3
        self.tag_to_evalvalue["1_6"] = -15
        self.tag_to_evalvalue["1_7"] = -12
        self.tag_to_evalvalue["2_0"] = 0
        self.tag_to_evalvalue["2_1"] = -3
        self.tag_to_evalvalue["2_2"] = 0
        self.tag_to_evalvalue["2_3"] = -1
        self.tag_to_evalvalue["2_4"] = -1
        self.tag_to_evalvalue["2_5"] = 0
        self.tag_to_evalvalue["2_6"] = -3
        self.tag_to_evalvalue["2_7"] = 0
        self.tag_to_evalvalue["3_0"] = -1
        self.tag_to_evalvalue["3_1"] = -3
        self.tag_to_evalvalue["3_2"] = -1
        self.tag_to_evalvalue["3_3"] = -1
        self.tag_to_evalvalue["3_4"] = -1
        self.tag_to_evalvalue["3_5"] = -1
        self.tag_to_evalvalue["3_6"] = -3
        self.tag_to_evalvalue["3_7"] = -1
        self.tag_to_evalvalue["4_0"] = -1
        self.tag_to_evalvalue["4_1"] = -3
        self.tag_to_evalvalue["4_2"] = -1
        self.tag_to_evalvalue["4_3"] = -1
        self.tag_to_evalvalue["4_4"] = -1
        self.tag_to_evalvalue["4_5"] = -1
        self.tag_to_evalvalue["4_6"] = -3
        self.tag_to_evalvalue["4_7"] = -1
        self.tag_to_evalvalue["5_0"] = 0
        self.tag_to_evalvalue["5_1"] = -3
        self.tag_to_evalvalue["5_2"] = 0
        self.tag_to_evalvalue["5_3"] = -1
        self.tag_to_evalvalue["5_4"] = -1
        self.tag_to_evalvalue["5_5"] = 0
        self.tag_to_evalvalue["5_6"] = -3
        self.tag_to_evalvalue["5_7"] = 0
        self.tag_to_evalvalue["6_0"] = -12
        self.tag_to_evalvalue["6_1"] = -15
        self.tag_to_evalvalue["6_2"] = -3
        self.tag_to_evalvalue["6_3"] = -3
        self.tag_to_evalvalue["6_4"] = -3
        self.tag_to_evalvalue["6_5"] = -3
        self.tag_to_evalvalue["6_6"] = -15
        self.tag_to_evalvalue["6_7"] = -12
        self.tag_to_evalvalue["7_0"] = 30
        self.tag_to_evalvalue["7_1"] = -12
        self.tag_to_evalvalue["7_2"] = 0
        self.tag_to_evalvalue["7_3"] = -1
        self.tag_to_evalvalue["7_4"] = -1
        self.tag_to_evalvalue["7_5"] = 0
        self.tag_to_evalvalue["7_6"] = -12
        self.tag_to_evalvalue["7_7"] = 30
        
    def init_board_setup(self):
        """盤面の座標と駒の初期配置を生成する"""
        self.coord_to_piece = {}
        BOARD_OFFSET = 15
        CELL_SIZE = 70
        WINDOW_SIZE = 590
        i = 0
        for h in range(BOARD_OFFSET, WINDOW_SIZE - BOARD_OFFSET, CELL_SIZE):
            j = 0
            for v in range(BOARD_OFFSET, WINDOW_SIZE - BOARD_OFFSET, CELL_SIZE):
                coord = (h, v, h + CELL_SIZE, v + CELL_SIZE)

                # 初期駒の設置
                if (j == 3 and i == 3) or (j == 4 and i == 4):
                    self.coord_to_piece[coord] = 1 # 黒
                elif (j == 3 and i == 4) or (j == 4 and i == 3):
                    self.coord_to_piece[coord] = 2 # 白
                else:
                    self.coord_to_piece[coord] = 0 # 駒なし
                j += 1
            i += 1   
        
        # コマが置けるかどうかの判断
    def check_avalable_hit(self, coord, view):
        # 初期化
        x = 0
        y = 0
        
        # コマが置いてあるかどうか
        self.avalable_hit = False
        if self.coord_to_piece.get(coord) == 0:
            tag = view.coord_to_tag[coord]
            x, y = map(int, tag.split("_"))
       
        # 置けるマスか判断
        self.check_piece_around(int(x), int(y), view, check_only=True)

    # コマが置けるかどうかの判断
    def check_random_hit(self, coord, view):
        # 初期化
        x = 0
        y = 0
        # コマが置いてあるかどうか
        # (1)コマが置いていない場合
        if self.coord_to_piece.get(coord) == 0:
            tag = view.coord_to_tag[coord]
            x, y = map(int, tag.split("_"))
            self.check_piece_around(int(x), int(y), view, check_only=False)

    # 可視化用メソッド
    def check_search_hit(self, coord, view):
        # 初期化
        x = 0
        y = 0
        # コマが置いてあるかどうか
        if self.coord_to_piece.get(coord) == 0:
            tag = view.coord_to_tag[coord]
            x, y = map(int, tag.split("_"))
            # 置けるマスか判断
            self.check_search_around(int(x), int(y), view)

    # 周辺に自分の駒があるか確認するメソッド(選択マスの8方向)
    def check_search_around(self, x, y, view):

        # 打ったプレーヤーの駒の色確認
        if self.turn == "first":
            # 黒色の場合
            my_color_num = 1
        elif self.turn == "second":
            # 白色の場合
            my_color_num = 2
        
        if not my_color_num: return
        for dx, dy in [(i, j) for i in range(-1, 2) for j in range(-1, 2) if not (i == 0 and j == 0)]:
            nx, ny = x + dx, y + dy
            if not (0 <= nx <= 7 and 0 <= ny <= 7): continue
            
            next_tag = f"{nx}_{ny}"
            next_coord = view.tag_to_coord[next_tag]
            piece_color_num = self.coord_to_piece[next_coord]

            if piece_color_num == my_color_num or piece_color_num == 0: continue

            if self.find_own_piece_in_direction(nx, ny, dx, dy, view):
                current_tag = f"{x}_{y}"
                if current_tag not in self.search_hit_list_tag:
                    self.search_hit_list_tag.append(current_tag)
        
    # 置ける可能性のあるマスの方向で検索
    def check_search_around_2(self, x, y, dx, dy, view):
        # 打ったプレーヤーの駒の色確認
        if self.turn == "first":
            # 黒色の場合
            my_color_num = 1
        elif self.turn == "second":
            # 白色の場合
            my_color_num = 2
        
            # 調べるマス取得
        if x + dx != -1 and x + dx != 8 and y + dy != -1 and y + dy != 8:

            maked_tag = str(x + dx) + "_" + str(y + dy)
            # 取得マスの状態確認
            piece_color_num = self.coord_to_piece[view.tag_to_coord[maked_tag]]

            # 調べるマスに駒がないマス、もしくは自分の駒がある時は置けない
            if piece_color_num == 0:
                pass

            # 調べたマスが自分の駒だったら
            elif piece_color_num == my_color_num:
                return True

            # 調べるマスに相手の駒がある場合
            elif piece_color_num != my_color_num:
                return self.check_search_around_2(x + dx, y + dy, dx, dy, view)

    def find_own_piece_in_direction(self, x, y, dx, dy, view):
        my_color_num = self.turn_to_piece.get(self.turn)
        cx, cy = x, y
        while 0 <= cx <= 7 and 0 <= cy <= 7:
            cx, cy = cx + dx, cy + dy
            if not (0 <= cx <= 7 and 0 <= cy <= 7): return False
            
            tag = f"{cx}_{cy}"
            coord = view.tag_to_coord[tag]
            piece_color = self.coord_to_piece[coord]
            
            if piece_color == 0: return False
            if piece_color == my_color_num: return True
        return False

    # 周辺に自分の駒があるか確認するメソッド(選択マスの8方向)
    def check_piece_around(self, x, y, view, check_only):

        # 打ったプレーヤーの駒の色確認
        if self.turn == "first":
            # 黒色の場合
            my_color_num = 1
        elif self.turn == "second":
            # 白色の場合
            my_color_num = 2
        
        if not my_color_num: return
        for dx, dy in [(i, j) for i in range(-1, 2) for j in range(-1, 2) if not (i == 0 and j == 0)]:
            nx, ny = x + dx, y + dy
            if not (0 <= nx <= 7 and 0 <= ny <= 7): continue
            
            next_tag = f"{nx}_{ny}"
            next_coord = view.tag_to_coord[next_tag]
            piece_color_num = self.coord_to_piece[next_coord]

            if piece_color_num == my_color_num or piece_color_num == 0: continue

            if self.find_own_piece_in_direction(nx, ny, dx, dy, view):
                if check_only:
                    self.avalable_hit = True
                    return
                        
                else:
                    current_tag = f"{x}_{y}"
                    if current_tag not in self.random_hit_list_tag:
                        self.random_hit_list_tag.append(current_tag)

    # 置ける可能性のあるマスの方向で検索
    def check_piece_around_2(self, x, y, dx, dy, view):
        # 打ったプレーヤーの駒の色確認
        if self.turn == "first":
            # 黒色の場合
            my_color_num = 1
        elif self.turn == "second":
            # 白色の場合
            my_color_num = 2
        
            # 調べるマス取得
        if x + dx != -1 and x + dx != 8 and y + dy != -1 and y + dy != 8:

            maked_tag = str(x + dx) + "_" + str(y + dy)
            # 取得マスの状態確認
            piece_color_num = self.coord_to_piece[view.tag_to_coord[maked_tag]]

            # 調べるマスに駒がないマス、もしくは自分の駒がある時は置けない
            if piece_color_num == 0:
                pass

            # 調べたマスが自分の駒だったら
            elif piece_color_num == my_color_num:
                self.avalable_hit = True
                return True

            # 調べるマスに相手の駒がある場合
            elif piece_color_num != my_color_num:
                return self.check_piece_around_2(x + dx, y + dy, dx, dy, view)

    def dohit(self, coord):

        # 思考時間を計算して記録
        if self.turn_start_time:
            elapsed_time = (datetime.now() - self.turn_start_time).total_seconds()
            if self.turn in self.turn_times:
                self.turn_times[self.turn].append(elapsed_time)

        # ターン数をインクリメント
        self.count += 1

        # 先攻が打ったら
        if self.turn == "first":
            self.coord_to_piece[coord] = 1

        # 後攻が打ったら
        else:
            self.coord_to_piece[coord] = 2
        
        # ログを記録
        self.play_log.append((self.count, self.turn, coord))

    # --- 反転させるメソッド ---
    def reverse_piece(self, coord, view):
        tag = view.coord_to_tag[coord]
        x, y = map(int, tag.split("_"))
        self.reverse_dic.clear()
        
        my_color_num = self.turn_to_piece.get(self.turn)
        for dx, dy in [(i, j) for i in range(-1, 2) for j in range(-1, 2) if not (i == 0 and j == 0)]:
            reversed_count_in_line = 0
            nx, ny = x + dx, y + dy
            to_reverse = []
            while 0 <= nx <= 7 and 0 <= ny <= 7:
                current_tag = f"{nx}_{ny}"
                current_coord = view.tag_to_coord[current_tag]
                piece_color = self.coord_to_piece[current_coord]
                if piece_color == 0:
                    break
                if piece_color == my_color_num:
                    for r_coord in to_reverse:
                        self.coord_to_piece[r_coord] = my_color_num
                        if my_color_num == 1: view.draw_piece_black(r_coord)
                        else: view.draw_piece_white(r_coord)
                    reversed_count_in_line = len(to_reverse)
                    break
                to_reverse.append(current_coord)
                nx, ny = nx + dx, ny + dy
            
            # この手での最大反転数を更新
            if reversed_count_in_line > 0 and self.turn in self.max_reversals:
                self.max_reversals[self.turn] = max(self.max_reversals[self.turn], reversed_count_in_line)
        
    # --- ひっくり返す駒があるか確認するメソッド(選択マスの8方向) ---
    def reverse_piece_around(self, x, y, view):
        # 打ったプレーヤーの駒の色確認
        if self.turn == "first":
            # 黒色の場合
            my_color_num = 1
        elif self.turn == "second":
            # 白色の場合
            my_color_num = 2
        
        # 周辺8方向の座標で検索
        for dx in range(-1, 2, 1):
            for dy in range(-1, 2, 1):
                # 存在しないマスをはじく
                if x + dx != -1 and x + dx != 8 and y + dy != -1 and y + dy != 8:
                    # dx = 0 and dy = 0をはじく
                    if not (dx == 0 and dy == 0):

                        maked_tag = str(x + dx) + "_" + str(y + dy)

                        # 周辺のマスの状態を確認する
                        # 調べるマスの状態取得
                        piece_color_num = self.coord_to_piece[view.tag_to_coord[maked_tag]]

                        # 調べるマスに相手の駒がある場合
                        if piece_color_num != my_color_num and piece_color_num != 0:
                            self.reverse_piece_around_2(x + dx, y + dy, dx, dy, view)
                else:
                    pass

    # --- ひっくり返すマスの方向で終点を検索 ---
    def reverse_piece_around_2(self, x, y, dx, dy, view):
        # 打ったプレーヤーの駒の色確認
        if self.turn == "first":
            # 黒色の場合
            my_color_num = 1
        elif self.turn == "second":
            # 白色の場合
            my_color_num = 2
        
        # 調べるマス取得
        if x + dx != -1 and x + dx != 8 and y + dy != -1 and y + dy != 8:

            maked_tag = str(x + dx) + "_" + str(y + dy)
            # 取得マスの状態確認
            piece_color_num = self.coord_to_piece[view.tag_to_coord[maked_tag]]

            # 調べたマスが自分の駒だったら
            if piece_color_num == my_color_num:
                # ひっくり返す終点を保存する辞書にタグと方向を追加
                dx_dy = str(dx) + "_" + str(dy)
                self.reverse_dic[maked_tag] = dx_dy

            # 調べるマスに相手の駒がある場合
            elif piece_color_num != my_color_num and piece_color_num != 0:
                return self.reverse_piece_around_2(x + dx, y + dy, dx, dy, view)

    # --- ターン変更メソッド ---
    def change_turn(self):
        # 先攻から後攻へターン変更
        if self.turn == "first":
            self.turn = "second"
        # 後攻から先攻にターン変更
        elif self.turn == "second":
            self.turn = "first"
        # 手を打ったかどうかフラグ初期化
        self.hit = False
        # 次のターンの開始時刻を記録
        self.turn_start_time = datetime.now()
        # 置けるマスがあるかどうかフラグ初期化
        self.avalable_hit = False
        # 終点保存辞書初期化
        self.reverse_dic = {}
        # 可視化メソッド用フラグ
        self.search_flag = False

    # --- ゲーム終了判断メソッド ---
    def finish_game(self):
        if self.pass_count >= 2:
            self.finish_flag = True
            return
        if all(p != 0 for p in self.coord_to_piece.values()):
            self.finish_flag = True
            return
        
    # --- ゲーム結果取得メソッド ---
    def get_result(self, view):
        # 駒のカウント変数
        black_count = sum(1 for p in self.coord_to_piece.values() if p == 1)
        white_count = sum(1 for p in self.coord_to_piece.values() if p == 2)

        # 統計情報をログウィジェットに表示
        stats_text = self.get_stats_text()
        view.log_text.insert(tkinter.END, "\n" + stats_text)
        view.log_text.see(tkinter.END)

        self.result_count = [black_count, white_count]

        filename = f"othello_log_{datetime.now():%Y%m%d_%H%M%S}.txt"
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write("--- Othello Play Log ---\n")
                log_content = view.log_text.get("1.0", tkinter.END)
                f.write(log_content)
                f.write("\n--- Result ---\n")
                f.write(f"先手 (黒): {black_count}\n")
                f.write(f"後手 (白): {white_count}\n")
                winner = "引き分け"
                if black_count > white_count: winner = "先手(黒)"
                elif white_count > black_count: winner = "後手(白)"
                f.write(f"勝者: {winner}\n")
            self.result_write_flag = True
        except Exception as e:
            print(f"ログファイルの保存に失敗しました: {e}")

    def get_stats_text(self):
        """統計情報を整形して文字列として返す"""
        stats = ["--- 統計情報 ---"]

        for turn, player_name in [("first", "先手(黒)"), ("second", "後手(白)")] :
            times = self.turn_times.get(turn)
            if times:
                avg_time = sum(times) / len(times)
                stats.append(f"[{player_name}]")
                stats.append(f" 平均時間: {avg_time:.2f}秒")
            else:
                stats.append(f"[{player_name}]")
                stats.append(f" 平均時間: N/A")
            
            max_rev = self.max_reversals.get(turn, 0)
            stats.append(f" 最大反転数: {max_rev}個")
        return "\n".join(stats)
              
# オセロをプレイ
def play_othello(): 
    # オセロクラスのインスタンスを生成
    game = Othello()
    game.view.setup_and_run()


if __name__ == "__main__":
    play_othello()
