# AIT Rescue Python

## 開発環境のセットアップ

### 必要な環境

- Python 3.14 以上
- [uv](https://docs.astral.sh/uv/) (Python パッケージマネージャー)
- [task](https://taskfile.dev/) (タスクランナー)
- [jq](https://stedolan.github.io/jq/) (JSON 処理ツール)
- Git

### uv のインストール

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### task のインストール

```bash
# macOS/Linux
brew install go-task/tap/go-task

# Windows
winget install Task.Task
```

### jq のインストール

```bash
# macOS/Linux
brew install jq
# Windows
winget install Jq.Jq
```

### セットアップ手順

1. リポジトリをクローン

```bash
git clone <repository-url>
cd ait-rescue-python
```

2. 仮想環境の作成と依存関係のインストール

```bash
uv sync
```

3. 仮想環境の有効化

```bash
source .venv/bin/activate  # Linux/macOSの場合
# .venv\Scripts\activate  # Windowsの場合
```

## プロジェクト構造

```
ait-rescue-python/
├── .vscode/          # VSCode設定ファイル
├── config/           # 設定ファイル
├── src/              # ソースコード
├── .gitignore        # Gitで無視するファイル一覧
├── .gitlab-ci.yml    # CI/CD設定ファイル
├── .python-version   # Pythonバージョン指定ファイル
├── main.py           # エージェントのエントリーポイント
├── pyproject.toml    # プロジェクト設定と依存関係
├── README.md         # このファイル
├── Taskfile.yaml     # タスク定義ファイル
└── uv.lock           # ロックファイル
```

## 開発ワークフロー

### 1. ブランチ戦略

- `main`: 本番環境用の安定版
- `develop`: 開発用の統合ブランチ
- `feature/xxx`: 新機能開発用
- `fix/xxx`: バグ修正用
- `hotfix/xxx`: 緊急修正用
- `docs/xxx`: ドキュメント関連の作業用
- `chore/xxx`: 雑多な作業用

### 2. 開発手順

1. develop ブランチから新しいブランチを作成

```bash
git checkout develop
git checkout -b feature/new-feature
```

2. コードを実装
3. テストを実行して確認
4. プルリクエストを作成

### 3. 依存関係の管理

新しいパッケージの追加:

```bash
uv add package-name
```

開発用依存関係の追加:

```bash
uv add --dev package-name
```

### 4. コミットメッセージ規約

- feat: 新機能
- fix: バグ修正
- docs: ドキュメント更新
- test: テスト追加・修正
- refactor: リファクタリング

例: `feat: エージェントの移動機能を追加`

### 5. コードのチェック

```bash
# コードのフォーマット
task format

# コードの静的解析
task lint

# 型チェック
task typecheck

# フォーマット+静的解析+型チェックを一括実行
task check
```

### 6. 動作確認

```bash
# エージェントの実行(事前計算データがある場合、自動で使うので注意)
task run

# 事前計算の実行
task precompute

# 事前計算データのクリア
task clear-precompute-data

# ログのクリア
task clear-logs

# エージェントの起動時の引数を変えたい場合
uv run python main.py <args>
```

## コーディング規約

### Python スタイル

- PEP 8 に準拠
- 関数名・変数名: snake_case
- ファイル名: snake_case
- クラス名: PascalCase
- 定数: UPPER_CASE

### ドキュメント

- [Google 形式の docstring](https://sphinxcontrib-napoleon.readthedocs.io/en/latest/example_google.html)を使用

## トラブルシューティング

### よくある問題

1. 依存関係のエラー
   - `uv sync`を実行して依存関係を再同期

2. uv が見つからない場合
   - uv が正しくインストールされているか確認
   - シェルを再起動して PATH を更新
