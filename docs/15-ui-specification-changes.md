# UI仕様変更まとめ

## 📋 元の提案（2026年5月31日）

### ページ構成（変更なし）
```
1. 🌍 環境ジェネレータ & バリデーター
2. 🧬 世代交代パイプライン & モニタリング
3. 📊 精度比較・ベンチマーク
```

---

## 🔄 変更が必要な箇所

### 1. ページ1：環境ジェネレータ & バリデーター

#### 元の仕様
- パラメータ設定：並列環境数、基本ズレ量スケール、非線形度、ガウシアンノイズ
- 2Dベクトル場（Quiver Plot）でボルト締め後のズレ方向を可視化
- 特定環境IDの深掘り（断面グラフ）

#### 変更内容
**A) パラメータ設定を簡略化**
- ❌ 削除：基本ズレ量スケール、非線形度、ガウシアンノイズ
- ✅ 維持：並列環境数のみ

**B) 2Dベクトル場の扱い**
- 選択肢1：**ダミー表示**（実際のボルトモデルには影響しない教育目的の可視化）
- 選択肢2：**削除**してパラメータ設定のみのシンプルなページに
- 選択肢3：**将来実装予定の注釈**を追加して残す

**C) 特定環境IDの深掘り**
- ✅ 維持：実験開始後に各環境の実際の挙動を可視化する機能として有用

#### 変更理由
1. **現在のボルトモデルは固定の線形変換のみ**
   - 非線形度やノイズパラメータを設定しても実際には反映されない
   - ユーザーに誤解を与える可能性がある

2. **ボルトモデルの多様性は将来的な拡張**
   - Phase 2以降でbolt-serviceを拡張する予定
   - 現時点では実装されていない機能をUIに含めるべきでない

3. **ページ1の役割を明確化**
   - 現状：「実験設定ページ」として機能
   - 将来：bolt-service拡張後に、環境パラメータの設定・可視化ページに進化

---

### 2. ページ2：世代交代パイプライン & モニタリング

#### 元の仕様
- コントロールパネル：学習開始、一時停止、中止ボタン
- 設定：総世代数、1世代あたりのエピソード数
- ステータス＆進捗バー
- リアルタイム学習曲線

#### 追加する設定項目

**A) モデル設定セクション（新規）**
```python
st.sidebar.markdown("### 🧠 モデル設定")

# 履歴ステップ数（重要！）
n_history_steps = st.sidebar.slider(
    "履歴ステップ数 (N)",
    min_value=1,
    max_value=10,
    value=3,
    help="過去何ステップの情報を使用するか。大きいほど環境適応力が向上する可能性がある"
)

# 隠れ層サイズ
hidden_dim = st.sidebar.selectbox(
    "隠れ層サイズ",
    options=[64, 128, 256, 512],
    index=1,  # デフォルト128
    help="モデルの表現力。大きいほど複雑なパターンを学習可能"
)

# 学習エポック数
epochs = st.sidebar.slider(
    "エポック数",
    min_value=10,
    max_value=100,
    value=20,
    help="学習の反復回数"
)

# 学習率（オプション）
learning_rate = st.sidebar.select_slider(
    "学習率",
    options=[1e-4, 5e-4, 1e-3, 5e-3, 1e-2],
    value=1e-3,
    format_func=lambda x: f"{x:.0e}"
)
```

**B) 実験設定の整理**
```python
st.sidebar.markdown("### 📦 データ収集設定")

n_parallel_envs = st.sidebar.slider(
    "並列環境数",
    min_value=10,
    max_value=1000,
    value=100,
    step=10,
    help="異なるボルトモデルで並行してデータを収集"
)

trials_per_env = st.sidebar.slider(
    "環境あたりの試行数",
    min_value=1,
    max_value=10,
    value=3,
    help="各環境で何回試行するか"
)

st.sidebar.markdown("### 🔁 世代交代設定")

n_generations = st.sidebar.slider(
    "総世代数",
    min_value=5,
    max_value=50,
    value=20
)

target_success_rate = st.sidebar.slider(
    "目標合格率 (%)",
    min_value=80,
    max_value=99,
    value=95,
    help="この合格率に達したら学習を早期終了"
)

early_stopping_patience = st.sidebar.slider(
    "早期停止の忍耐値",
    min_value=2,
    max_value=10,
    value=3,
    help="何世代改善がなければ停止するか"
)
```

**C) メイン表示エリアに追加**
```python
# 現在の設定サマリーを表示
with st.expander("📋 現在の実験設定", expanded=True):
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("並列環境数", f"{n_parallel_envs}")
        st.metric("履歴ステップ数", f"N={n_history_steps}")
    
    with col2:
        st.metric("総世代数", f"{n_generations}")
        st.metric("隠れ層サイズ", f"{hidden_dim}")
    
    with col3:
        st.metric("総データ数（予定）", 
                  f"{n_parallel_envs * trials_per_env * n_generations * 5}") # 平均5ステップと仮定
        st.metric("エポック数", f"{epochs}")

# モデルアーキテクチャの可視化（オプション）
st.subheader("🧠 モデルアーキテクチャ")
input_dim = 10 * 6 + 2  # MAX_N=10固定
st.code(f"""
Input: {input_dim}次元 (過去{n_history_steps}ステップ + 現在位置)
  ↓
Linear({input_dim} → {hidden_dim}) → ReLU
  ↓
Linear({hidden_dim} → {hidden_dim}) → ReLU
  ↓
Linear({hidden_dim} → {hidden_dim//2}) → ReLU
  ↓
Linear({hidden_dim//2} → 2)  [delta_x, delta_y]
""", language="text")
```

#### 変更理由
1. **履歴ステップ数Nが学習の核心パラメータ**
   - 環境適応能力に直結（N=1 vs N=3で大きく性能が変わる可能性）
   - ユーザーが実験で最適値を探索する必要がある

2. **モデルサイズの調整可能性**
   - 環境の複雑さやデータ量に応じて最適なサイズが異なる
   - 過学習と表現力のトレードオフをユーザーが制御

3. **実験設定の透明性向上**
   - どんなモデルで学習しているか一目で分かる
   - 後で「なぜこの結果になったか」を追跡可能

---

### 3. ページ3：精度比較・ベンチマーク

#### 元の仕様
- 実験選択（複数選択可能）
- リーダーボードテーブル
- 重ね合わせ折れ線グラフ
- 感度分析（しきい値 vs 合格率）

#### 追加・変更する項目

**A) リーダーボードテーブルに列を追加**
```python
# 元のテーブル
| 実験ID | モデル名 | 環境難易度 | 最終世代合格率 | 平均調整ステップ数 |

# 新しいテーブル
| 実験ID | モデル名 | N | 隠れ層 | 環境数 | 世代数 | データ総数 | 最終合格率 | 平均ステップ | 学習時間 |
|--------|----------|---|--------|--------|--------|-----------|-----------|-------------|----------|
| exp_001| MLP      | 1 | 128    | 100    | 20     | 10,000    | 85%       | 4.2         | 5m 23s   |
| exp_002| MLP      | 3 | 128    | 100    | 20     | 10,000    | 92%       | 3.5         | 6m 12s   |
| exp_003| MLP      | 5 | 128    | 100    | 20     | 10,000    | 94%       | 3.2         | 7m 45s   |
| exp_004| MLP      | 3 | 256    | 100    | 20     | 10,000    | 95%       | 3.0         | 8m 31s   |
| exp_005| MLP      | 3 | 128    | 200    | 20     | 20,000    | 96%       | 2.8         | 12m 18s  |
```

**B) N値による性能比較セクション（新規）**
```python
st.subheader("📊 履歴ステップ数（N）の影響分析")

# 他の条件を固定してN値だけ変えた実験を比較
n_analysis_data = df[df['hidden_dim'] == 128]  # 隠れ層128に絞る

fig = px.line(
    n_analysis_data,
    x='n_history',
    y='final_success_rate',
    color='n_environments',
    markers=True,
    title='N値と合格率の関係',
    labels={
        'n_history': '履歴ステップ数 (N)',
        'final_success_rate': '最終合格率 (%)',
        'n_environments': '環境数'
    }
)
st.plotly_chart(fig)

# 統計的分析
st.markdown("**分析結果**")
col1, col2 = st.columns(2)

with col1:
    st.metric(
        "最適なN値",
        value="N=5",
        delta="+9% (vs N=1)",
        help="このデータセットで最も高い合格率を達成したN値"
    )

with col2:
    st.metric(
        "収束効率",
        value="N=3",
        help="学習時間と性能のバランスが最良"
    )
```

**C) モデルサイズ vs 性能の可視化（新規）**
```python
st.subheader("🧠 モデルサイズの影響")

fig = px.scatter(
    df,
    x='hidden_dim',
    y='final_success_rate',
    size='data_total',
    color='n_history',
    hover_data=['experiment_id', 'training_time'],
    title='隠れ層サイズと合格率',
    labels={
        'hidden_dim': '隠れ層サイズ',
        'final_success_rate': '最終合格率 (%)',
        'data_total': 'データ総数',
        'n_history': 'N値'
    }
)
st.plotly_chart(fig)

st.info("""
**💡 解釈のヒント**
- データ量が多い場合、大きなモデル（256, 512）が有利
- データ量が少ない場合、小さなモデル（64, 128）が過学習を防ぐ
- N値が大きい場合、より大きなモデルが必要
""")
```

**D) ハイパーパラメータの相関マトリックス（新規）**
```python
st.subheader("🔗 パラメータ相関分析")

# 相関マトリックス
correlation_params = [
    'n_history', 'hidden_dim', 'n_environments', 
    'n_generations', 'final_success_rate', 'avg_steps'
]
corr_matrix = df[correlation_params].corr()

fig = px.imshow(
    corr_matrix,
    text_auto='.2f',
    aspect='auto',
    title='ハイパーパラメータの相関',
    labels=dict(color="相関係数")
)
st.plotly_chart(fig)

st.markdown("""
**📈 注目すべき相関**
- `n_history` ↔ `final_success_rate`: 強い正の相関 → N値を増やせば性能向上
- `hidden_dim` ↔ `training_time`: 強い正の相関 → 大きなモデルは学習に時間がかかる
- `n_environments` ↔ `final_success_rate`: 中程度の正の相関 → データの多様性が重要
""")
```

#### 変更理由
1. **N値が最重要な実験パラメータ**
   - どのN値が最適かを明確に示す必要がある
   - 単なる数値比較でなく、視覚的に傾向を理解

2. **実験の再現性と追跡可能性**
   - 全てのハイパーパラメータを記録
   - 「なぜこの実験が良かったのか」を分析可能

3. **科学的な実験設計の支援**
   - 相関分析で次の実験の方針を決定
   - 無駄な実験を減らす

---

## 🎯 実装優先順位

### Phase 1: 最小限の動作デモ（ダミーデータ）
- [ ] 3ページの骨格
- [ ] ページ1: 並列環境数設定のみ（ダミー可視化は後回し）
- [ ] ページ2: 基本的な設定項目 + ダミーの進捗表示
- [ ] ページ3: ダミーデータでの比較表示

### Phase 2: バックエンド統合
- [ ] ページ2: 実際のオーケストレーターと接続
- [ ] N値、hidden_dimをtrainerに渡す
- [ ] 実験データの保存・読み込み

### Phase 3: 高度な分析機能
- [ ] ページ3: N値分析、相関マトリックス
- [ ] ページ1: 実環境データの可視化

---

## 📝 技術的な注意事項

### 1. Streamlitの状態管理
```python
# 実験設定をsession_stateで保持
if 'experiment_config' not in st.session_state:
    st.session_state.experiment_config = {
        'n_history': 3,
        'hidden_dim': 128,
        'n_parallel_envs': 100,
        # ...
    }

# ページ遷移しても設定が消えないように
```

### 2. リアルタイム更新の実装
```python
# ポーリング方式（3秒ごと）
import time

placeholder = st.empty()

while job_status != 'completed':
    with placeholder.container():
        status = fetch_job_status(job_id)
        st.metric("進捗", f"{status['progress']}%")
        st.progress(status['progress'] / 100)
    
    time.sleep(3)
    st.rerun()  # Streamlitを再実行
```

### 3. 大量データの扱い
```python
# 実験数が多い場合、ページング
page_size = 20
page = st.number_input("ページ", 1, total_pages)
experiments_to_show = experiments[(page-1)*page_size : page*page_size]
st.dataframe(experiments_to_show)
```

---

## ✅ 最終決定事項（2026年5月31日確定）

### 判断1: ページ1の2Dベクトル場
**決定**: Option C-1（一様な矢印を正直に表示）

実装内容:
```python
# 全座標で同じ方向・大きさの固定ベクトル（現状を正直に表示）
x = np.linspace(-0.5, 0.5, 10)
y = np.linspace(-0.5, 0.5, 10)
X, Y = np.meshgrid(x, y)
U = np.ones_like(X) * 0.1  # 固定シフト (例)
V = np.ones_like(Y) * 0.1

fig = go.Figure(data=go.Cone(x=X.flatten(), y=Y.flatten(), 
                              u=U.flatten(), v=V.flatten()))
st.plotly_chart(fig)

st.info("""
ℹ️ **現在の実装状況**
- Phase 1: 固定線形変換モデル（全領域で一様なズレ）
- Phase 3予定: 位置依存・非線形ズレモデルに対応
""")
```

理由: 
- 静止画プレースホルダーより「触っている感」が出る
- Phase 3で非線形に変わった際の進化が視覚的に分かる
- Sim-to-Real検証時に「現状はシンプル」と明示され混乱を防ぐ

### 判断2: ページ2のリアルタイム更新
**決定**: ポーリング + `st.session_state` + **学習中UIロック**

実装内容:
```python
# 学習中フラグ
if 'job_running' not in st.session_state:
    st.session_state.job_running = False

# サイドバーの設定（学習中はdisabled）
n_history = st.sidebar.slider(
    "履歴ステップ数 (N)",
    min_value=1,
    max_value=10,
    value=3,
    disabled=st.session_state.job_running  # ← 重要！
)

hidden_dim = st.sidebar.selectbox(
    "隠れ層サイズ",
    [64, 128, 256],
    disabled=st.session_state.job_running
)

# 学習開始
if st.button("学習開始", disabled=st.session_state.job_running):
    job_id = start_learning_job(config)
    st.session_state.job_id = job_id
    st.session_state.job_running = True
    st.rerun()

# ポーリング更新
if st.session_state.job_running:
    status = poll_job_status(st.session_state.job_id)
    
    progress_placeholder = st.empty()
    with progress_placeholder.container():
        st.metric("進捗", f"{status['progress']}%")
        st.progress(status['progress'] / 100)
    
    if status['status'] == 'completed':
        st.session_state.job_running = False
        st.success("学習完了！")
        st.rerun()
    else:
        time.sleep(3)
        st.rerun()
```

理由:
- WebSocketは不要（オーバースペック）
- UIロックでユーザーの誤操作とカクつきを完全に防ぐ
- 3秒ポーリングで十分なUX

### 判断3: ページ3の影響度バーチャート
**決定**: 相関係数ベース（正負を保持）

実装内容:
```python
# 相関係数を計算（正負の方向を保持）
correlations = {
    'N値': df['n_history'].corr(df['final_success_rate']),
    '隠れ層サイズ': df['hidden_dim'].corr(df['final_success_rate']),
    '環境数': df['n_environments'].corr(df['final_success_rate']),
    'エポック数': df['epochs'].corr(df['final_success_rate']),
}

# 横棒グラフ（正負の色分け）
fig = px.bar(
    x=list(correlations.values()),
    y=list(correlations.keys()),
    orientation='h',
    title='最終合格率への影響度（相関係数）',
    labels={'x': '相関係数', 'y': 'パラメータ'},
    color=list(correlations.values()),  # 正負で色分け
    color_continuous_scale=['red', 'white', 'blue']
)
st.plotly_chart(fig)
```

理由:
- グリッドサーチ的な実験設計なので多重共線性が低い
- 相関係数で十分に傾向が掴める
- 正負の方向が重要（絶対値にしない）

### 判断4: ページ3の凡例命名
**決定**: `N=3, H=128, Env=100`形式の略記

実装内容:
```python
def generate_model_label(row):
    """実験の識別ラベルを生成"""
    # モデル名が全てMLPなら省略可能
    parts = []
    if row.get('model_name') and row['model_name'] != 'MLP':
        parts.append(row['model_name'])
    parts.append(f"N={row['n_history']}")
    parts.append(f"H={row['hidden_dim']}")
    parts.append(f"Env={row['n_environments']}")
    return ", ".join(parts)

df['label'] = df.apply(generate_model_label, axis=1)

fig = px.line(
    df,
    x='generation',
    y='success_rate',
    color='label',
    title='世代ごとの合格率推移'
)
```

理由:
- エンジニアにとって最も分かりやすい「共通言語」
- 固定パラメータ（全部MLPなど）は省略してスッキリ

### 判断5: ページ2の入力ベクトル説明
**決定**: 表形式 + 色付きブロック帯

実装内容:
```python
st.markdown("### 📊 入力データの構造")

# 色付きブロック帯（視覚的補助）
unused_dim = (10 - n_history) * 6
history_dim = n_history * 6
current_dim = 2

col1, col2, col3 = st.columns([unused_dim, history_dim, current_dim])
with col1:
    st.markdown(f'<div style="background-color:#CCCCCC; padding:10px; text-align:center;">ゼロパディング<br>{unused_dim}次元</div>', unsafe_allow_html=True)
with col2:
    st.markdown(f'<div style="background-color:#4169E1; color:white; padding:10px; text-align:center;">過去履歴<br>{history_dim}次元</div>', unsafe_allow_html=True)
with col3:
    st.markdown(f'<div style="background-color:#32CD32; color:white; padding:10px; text-align:center;">現在位置<br>{current_dim}次元</div>', unsafe_allow_html=True)

st.markdown(f"""
**現在の設定**: N={n_history}, 合計入力次元数={10*6+2}次元
""")

# 表形式で詳細説明
input_structure = pd.DataFrame([
    {"ステップ": "Step -9〜-4", "次元数": f"{unused_dim}", "内容": "ゼロパディング（未使用領域）"},
    {"ステップ": f"Step -{n_history}〜-1", "次元数": f"{history_dim}", "内容": "過去の試行履歴（各6次元: spot_before x,y, delta x,y, spot_after x,y）"},
    {"ステップ": "現在", "次元数": f"{current_dim}", "内容": "現在のspot位置 (x, y)"},
])

st.dataframe(input_structure, use_container_width=True)

st.info(f"""
💡 **ポイント**: N={n_history}の場合、実際に使われるのは{history_dim+current_dim}次元ですが、
モデルは最大N=10に対応できるよう{10*6+2}次元の入力を受け取ります。
""")
```

理由:
- パディング構造が視覚的に一発で理解できる
- 表形式で詳細も確認可能
- N値を変えたときの変化が直感的

### 判断6-7: learning_rate, batch_size
**決定**: 非公開（固定）

- learning_rate: 1e-3固定
- batch_size: データサイズに応じて自動調整

理由: 初期フェーズでは複雑化を避ける

---

## ✅ まとめ

### 変更のポイント
1. **ページ1**: ボルトモデル関連の設定を簡略化（現状に合わせる）
2. **ページ2**: モデル設定（N値、hidden_dim等）を追加
3. **ページ3**: N値分析、相関分析を追加

### 変更の理由
- 技術的議論により、**履歴ステップ数Nが環境適応の核心**と判明
- 現在のボルトモデルは固定 → 将来拡張するまで無駄な設定は避ける
- 実験の科学的再現性と分析能力の向上

### 元の構想との整合性
- ✅ 3ページ構成は維持
- ✅ 世代交代とメタ学習のコンセプトは維持
- ✅ 並列環境での学習は維持
- 🔧 パラメータの具体的内容を技術実装に合わせて調整
