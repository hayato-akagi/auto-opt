# Phase 2: バックエンド拡張 - 全体設計と実装プラン

## 🎯 目標

Phase 1で完成したUIと連携し、以下を実現する：
1. **N値可変対応**：履歴ステップ数1〜10を動的に扱える
2. **モデルサイズ可変**：hidden_dim（64/128/256/512）を設定可能
3. **世代管理**：Gen0→Gen1→Gen2+の自動パイプライン
4. **実験管理**：複数実験の記録と比較

---

## 📐 アーキテクチャ設計

### 全体フロー

```
[Streamlit UI] ← HTTP → [collection-orchestrator] ← HTTP → [trainer]
                              ↓                              ↓
                         [recipe-service]              [model-store]
                              ↓
                    [simple-controller]
                    [ai-controller]
```

### データフロー（1世代）

```
Step 1: データ収集
  UI → orchestrator: start_generation(exp_id, gen_id, n_envs, n_trials, controller_type)
  orchestrator → simple/ai-controller: 並列実行（n_envs個）
  controller → recipe-service: 試行データを保存

Step 2: 学習
  orchestrator → trainer: train(exp_id, gen_id, n_history, hidden_dim, epochs)
  trainer → recipe-service: Gen0〜現在までのデータを取得
  trainer: 学習実行
  trainer → model-store: モデル保存（将来）または /app/models/ に保存

Step 3: 次世代準備
  orchestrator: Gen+1用の設定を準備
  → ai-controllerに新しいモデルパスを指定
```

---

## 🔧 実装方針

### 原則

1. **後方互換性**: 既存のN=1実装を壊さない
2. **段階的実装**: 各コンポーネントを独立してテスト
3. **設定の外部化**: ハイパーパラメータをリクエストで受け取る

### データ構造

#### 実験メタデータ（新規）

```python
# recipe-serviceに保存（experiment拡張）
{
  "experiment_id": "exp_001",
  "name": "N=3, H=128, Env=100",
  "created_at": "2026-05-31T12:00:00Z",
  "config": {
    "n_parallel_envs": 100,
    "trials_per_env": 3,
    "n_generations": 20,
    "model_config": {
      "n_history": 3,
      "hidden_dim": 128,
      "epochs": 20,
      "learning_rate": 1e-3
    },
    "stopping_config": {
      "target_success_rate": 0.95,
      "early_stopping_patience": 3
    }
  },
  "generations": [
    {
      "gen_id": 0,
      "controller": "simple-controller",
      "status": "completed",
      "trials": ["trial_001", "trial_002", ...],
      "metrics": {
        "success_rate": 0.85,
        "avg_steps": 4.2,
        "total_samples": 1500
      }
    },
    {
      "gen_id": 1,
      "controller": "ai-controller",
      "model_version": "exp_001_gen1",
      "status": "completed",
      "trials": [...],
      "metrics": {
        "success_rate": 0.92,
        "avg_steps": 3.5,
        "total_samples": 3000
      }
    }
  ],
  "status": "running" | "completed" | "failed"
}
```

---

## 📦 コンポーネント別実装計画

### 1️⃣ trainer拡張

#### 変更ファイル

**A) `app/data.py`**

```python
def extract_features_with_history(
    steps: list[dict],
    n_history: int = 3,
    max_history: int = 10
) -> np.ndarray:
    """
    過去n_historyステップの特徴量を抽出（最大max_history次元）
    
    Args:
        steps: 試行のステップリスト
        n_history: 使用する履歴ステップ数
        max_history: モデルの最大対応ステップ数（固定）
    
    Returns:
        shape=(max_history*6+2,) の特徴量ベクトル
    """
    features = []
    
    # ゼロパディング（未使用領域）
    for _ in range(max_history - min(len(steps) - 1, n_history)):
        features.extend([0.0] * 6)
    
    # 実際の履歴データ（最新n_history個）
    if len(steps) > 1:
        start_idx = max(0, len(steps) - 1 - n_history)
        for i in range(start_idx, len(steps) - 1):
            step = steps[i]
            features.extend([
                step['spot_before']['x'],
                step['spot_before']['y'],
                step['delta']['x'],
                step['delta']['y'],
                step['spot_after']['x'],
                step['spot_after']['y'],
            ])
    
    # 現在のスポット位置
    current = steps[-1]
    features.extend([
        current['spot_before']['x'],
        current['spot_before']['y']
    ])
    
    return np.array(features)


def collect_training_data_v2(
    experiments: list[dict],
    get_trial_steps: callable,
    n_history: int = 3,
    max_history: int = 10,
    only_converged: bool = True
) -> tuple[np.ndarray, np.ndarray]:
    """
    N値可変対応版のデータ収集
    
    Returns:
        features: shape=(N_samples, max_history*6+2)
        labels: shape=(N_samples, 2)
    """
    # 実装...
```

**変更点**:
- `n_history`パラメータを追加
- `extract_features`を`extract_features_with_history`に置き換え
- 常に62次元（10*6+2）を返す

**B) `app/train.py`**

```python
class BoltShiftMLP(nn.Module):
    """N値可変対応のMLP"""
    
    def __init__(
        self,
        max_history_steps: int = 10,
        hidden_dim: int = 128,
        output_dim: int = 2
    ):
        super().__init__()
        input_dim = max_history_steps * 6 + 2  # 62次元
        
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, output_dim),
        )


@dataclass
class TrainingConfig:
    """学習設定（拡張版）"""
    epochs: int = 20
    batch_size: int = 32
    learning_rate: float = 1e-3
    val_split: float = 0.1
    hidden_dim: int = 128
    max_history_steps: int = 10  # 固定
    n_history: int = 3  # 実際に使用するステップ数
    device: str = "cpu"


def save_model(
    model: nn.Module,
    path: Path,
    model_type: str,
    config: TrainingConfig,
    feature_stats: dict,
    metadata: dict
) -> None:
    """モデル保存（N値とhidden_dimを追加）"""
    torch.save({
        'model_state_dict': model.state_dict(),
        'model_type': model_type,
        'hidden_dim': config.hidden_dim,
        'max_history_steps': config.max_history_steps,
        'n_history': config.n_history,  # 学習時のN値を記録
        'feature_stats': feature_stats,
        'metadata': metadata,
    }, path)
```

**変更点**:
- `hidden_dim`を可変に
- `n_history`を設定とメタデータに追加
- 保存時に全パラメータを記録

**C) `app/models.py`**

```python
class TrainRequest(BaseModel):
    """学習リクエスト（拡張版）"""
    experiment_ids: list[str] = Field(..., min_length=1)
    model_type: str = Field(default="mlp")
    epochs: int = Field(default=20, ge=1, le=200)
    batch_size: int = Field(default=32, ge=1, le=512)
    
    # 新規追加
    n_history: int = Field(default=3, ge=1, le=10)
    hidden_dim: int = Field(default=128, gt=0)
    learning_rate: float = Field(default=1e-3, gt=0)
    only_converged: bool = Field(default=True)
```

**D) `app/main.py`**

リクエストから`n_history`と`hidden_dim`を受け取り、`job_runner`に渡す。

---

### 2️⃣ ai-controller拡張

#### 変更ファイル

**A) `app/logic.py`**

```python
def extract_features_for_inference(
    prev_steps: list[dict] | None,
    current_spot: dict,
    n_history: int = 3,
    max_history: int = 10
) -> np.ndarray:
    """
    推論用の特徴量抽出（N値可変対応）
    
    Args:
        prev_steps: 過去のステップ（最新n_history個まで使用）
        current_spot: 現在のスポット位置
        n_history: 使用するステップ数
        max_history: モデルの最大対応ステップ数
    
    Returns:
        shape=(max_history*6+2,) の特徴量
    """
    features = []
    
    # パディング
    actual_history = len(prev_steps) if prev_steps else 0
    padding_count = max_history - min(actual_history, n_history)
    
    for _ in range(padding_count):
        features.extend([0.0] * 6)
    
    # 実データ
    if prev_steps:
        start_idx = max(0, len(prev_steps) - n_history)
        for step in prev_steps[start_idx:]:
            features.extend([
                step['spot_before']['x'],
                step['spot_before']['y'],
                step['delta']['x'],
                step['delta']['y'],
                step['spot_after']['x'],
                step['spot_after']['y'],
            ])
    
    # 現在位置
    features.extend([current_spot['x'], current_spot['y']])
    
    return np.array(features)
```

**B) `app/model.py`**

```python
class ModelManager:
    """N値対応のModelManager"""
    
    def __init__(
        self,
        *,
        model_type: str = "mlp",
        model_path: Path | None = None,
        device: str = "cpu",
    ):
        # ...既存のコード...
        self._n_history: int | None = None  # モデルの学習時N値
        self._max_history_steps: int = 10  # 固定
    
    def load_model(self, model_path: Path) -> None:
        """モデル読み込み（N値情報を取得）"""
        checkpoint = torch.load(model_path, weights_only=False)
        
        self._hidden_dim = checkpoint.get('hidden_dim', 64)
        self._max_history_steps = checkpoint.get('max_history_steps', 10)
        self._n_history = checkpoint.get('n_history', 3)  # 学習時のN値
        
        # モデル構築
        model = BoltShiftMLP(
            max_history_steps=self._max_history_steps,
            hidden_dim=self._hidden_dim
        )
        model.load_state_dict(checkpoint['model_state_dict'])
        # ...
```

**C) `app/models.py`**

```python
class AiControllerConfig(BaseModel):
    """AI Controller設定（拡張版）"""
    model_type: str = Field(default="baseline_only")
    model_version: str | None = Field(default=None)
    model_path: str | None = Field(default=None)
    
    # 新規追加（推論時に明示的にN値を指定可能）
    n_history: int | None = Field(default=None, ge=1, le=10)
    
    # 既存のパラメータ...
```

---

### 3️⃣ collection-orchestrator拡張

新規ファイル: `app/generation_manager.py`

```python
"""世代管理ロジック"""

from dataclasses import dataclass
from enum import Enum

class GenerationPhase(str, Enum):
    """世代のフェーズ"""
    PENDING = "pending"
    COLLECTING = "collecting"  # データ収集中
    TRAINING = "training"      # 学習中
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class GenerationConfig:
    """1世代の設定"""
    gen_id: int
    experiment_id: str
    controller: str  # "simple-controller" or "ai-controller"
    model_path: str | None
    n_parallel_envs: int
    trials_per_env: int


class GenerationOrchestrator:
    """世代交代を管理"""
    
    def __init__(
        self,
        simple_controller_url: str,
        ai_controller_url: str,
        trainer_url: str,
        recipe_service_url: str,
    ):
        # クライアント初期化...
    
    async def run_generation_pipeline(
        self,
        experiment_id: str,
        n_generations: int,
        n_parallel_envs: int,
        trials_per_env: int,
        model_config: dict,
        stopping_config: dict
    ) -> dict:
        """
        世代交代パイプラインを実行
        
        Flow:
          Gen0: simple-controller でデータ収集
          → train(Gen0データ) → model_v1
          Gen1: ai-controller(model_v1) でデータ収集
          → train(Gen0+Gen1データ) → model_v2
          Gen2: ai-controller(model_v2) でデータ収集
          ...
        """
        results = []
        
        for gen_id in range(n_generations):
            # Step 1: データ収集
            controller = "simple-controller" if gen_id == 0 else "ai-controller"
            model_path = None if gen_id == 0 else results[gen_id-1]['model_path']
            
            gen_result = await self._run_generation(
                gen_id=gen_id,
                experiment_id=experiment_id,
                controller=controller,
                model_path=model_path,
                n_parallel_envs=n_parallel_envs,
                trials_per_env=trials_per_env
            )
            
            # Step 2: 学習
            if gen_id < n_generations - 1:  # 最後以外は学習
                train_result = await self._train_generation(
                    experiment_id=experiment_id,
                    gen_id=gen_id,
                    model_config=model_config
                )
                gen_result['model_path'] = train_result['model_path']
                gen_result['train_metrics'] = train_result['metrics']
            
            results.append(gen_result)
            
            # Step 3: 早期停止判定
            if self._should_stop(results, stopping_config):
                break
        
        return {
            'experiment_id': experiment_id,
            'total_generations': len(results),
            'results': results
        }
```

---

## 🗂️ API設計

### collection-orchestrator 新規エンドポイント

```python
POST /experiments/pipeline
{
  "experiment_id": "exp_001",
  "config": {
    "n_parallel_envs": 100,
    "trials_per_env": 3,
    "n_generations": 20,
    "model_config": {
      "n_history": 3,
      "hidden_dim": 128,
      "epochs": 20
    },
    "stopping_config": {
      "target_success_rate": 0.95,
      "early_stopping_patience": 3
    }
  }
}

Response:
{
  "job_id": "pipeline_job_001",
  "status": "running",
  "experiment_id": "exp_001"
}
```

```python
GET /experiments/pipeline/{job_id}

Response:
{
  "job_id": "pipeline_job_001",
  "status": "running",
  "current_generation": 5,
  "total_generations": 20,
  "progress": 0.25,
  "generations": [
    {
      "gen_id": 0,
      "status": "completed",
      "metrics": {...}
    },
    ...
  ]
}
```

---

## 📅 実装スケジュール

### Week 1: Trainer拡張（3-4日）

- [ ] Day 1: data.py拡張（N値対応）+ テスト
- [ ] Day 2: train.py拡張（hidden_dim可変）+ テスト
- [ ] Day 3: job_runner/main.py統合 + E2Eテスト
- [ ] Day 4: Docker更新 + 動作確認

### Week 2: AI-Controller拡張（2-3日）

- [ ] Day 5: logic.py/model.py拡張 + テスト
- [ ] Day 6: main.py統合 + E2Eテスト
- [ ] Day 7: Docker更新 + trainer連携テスト

### Week 3: Orchestrator拡張（3-4日）

- [ ] Day 8: generation_manager.py実装
- [ ] Day 9: API endpoint追加 + テスト
- [ ] Day 10: 全体E2Eテスト

### Week 4: UI統合（2-3日）

- [ ] Day 11: StreamlitとAPI接続
- [ ] Day 12: リアルタイム更新実装
- [ ] Day 13: 総合テスト + バグ修正

---

## 🧪 テスト戦略

### Unit Test

各コンポーネントで：
- N=1, 3, 5の入力に対する動作確認
- hidden_dim=64, 128, 256での学習
- パディングの正しさ

### Integration Test

- trainer → ai-controller: モデル受け渡し
- orchestrator → trainer: 学習ジョブ管理
- 世代0→1→2の連鎖

### E2E Test

```python
# test_e2e_pipeline.py
def test_full_pipeline():
    """3世代のパイプライン"""
    # Gen0: simple-controller
    # Gen1: 学習 → ai-controller
    # Gen2: 再学習 → ai-controller
    # 各世代でメトリクス改善を確認
```

---

## ⚠️ リスクと対策

### リスク1: N値が大きいと学習が不安定

**対策**: 
- 初期実装はN=1,3,5に限定
- N=10は実験的機能として後回し

### リスク2: 世代管理の状態が複雑

**対策**:
- 各世代をステートマシンで管理
- recipe-serviceに状態を永続化

### リスク3: UI更新のタイムラグ

**対策**:
- ポーリング間隔を3秒に設定
- 進捗バーで視覚的フィードバック

---

## 📌 次のアクション

**推奨**: Week 1から順次実装

1. **今から開始**: trainer拡張（data.py）
2. **並行作業可能**: テストコードの準備
3. **後回し**: orchestrator（trainer完成後）

**どこから始めますか？**
