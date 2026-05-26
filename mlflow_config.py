import mlflow
import os
from dotenv import load_dotenv

load_dotenv()

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5001")


def setup_mlflow(experiment_name: str):
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(experiment_name)


def log_whisper_metrics(wer: float, loss: float, epoch: int):
    mlflow.log_metrics({
        "wer": wer,
        "loss": loss,
        "epoch": epoch
    })


def log_whisper_params(model_size: str, languages: list,
                        num_samples: int, batch_size: int,
                        learning_rate: float, epochs: int):
    mlflow.log_params({
        "model_size": model_size,
        "languages": str(languages),
        "num_samples": num_samples,
        "batch_size": batch_size,
        "learning_rate": learning_rate,
        "epochs": epochs
    })


def register_model(run_id: str, model_name: str,
                   model_path: str, wer: float):
    mlflow.register_model(
        f"runs:/{run_id}/whisper-provoc",
        model_name
    )
    print(f"Model {model_name} registered with WER: {wer:.4f}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "list-models":
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        client = mlflow.tracking.MlflowClient()
        for model in client.search_registered_models():
            print(f"\nModel: {model.name}")
            for version in model.latest_versions:
                tags = version.tags
                print(f"  Version {version.version} — "
                      f"WER: {tags.get('wer', 'N/A')} — "
                      f"Status: {version.status}")
