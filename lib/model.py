import torch
import torch.nn as nn

from lib.nn import MLP, BiLSTM, Embedding
from lib.util import Metric, unpad, flatten, get_device


class Model(nn.Module):

    #
    #
    #  -------- init -----------
    #
    def __init__(self, config: dict, embedding_data: list):
        super().__init__()

        # save config
        self.config = config
        self.metric = Metric()

        self.embedding = Embedding(data=embedding_data, **self.config["embedding"])

        # BiLSTM to calculate contextualized word embedding
        self.context = BiLSTM(
            in_size=self.config["embedding"]["dimension"],
            hid_size=config["lstm"]["hid_size"],
            depth=config["lstm"]["depth"],
            dropout=config["lstm"]["dropout"],
        )

        # MLP to calculate the POS tags
        self.score = MLP(
            in_size=config["lstm"]["hid_size"] * 2,
            hid_size=config["score"]["hid_size"],
            out_size=2,
            dropout=config["score"]["dropout"],
        )

    #
    #
    #  -------- forward -----------
    #
    def forward(self, batch: list) -> list:

        embed_batch: list = self.embedding.forward_batch(batch)

        # Contextualize embedding with BiLSTM
        pad_context, mask = self.context(embed_batch)

        # Calculate the sentiment for each word
        pad_scores = self.score(pad_context)

        # Sum individual values to sentence prediction
        return [torch.sum(pred, dim=0, keepdim=True) for pred in unpad(pad_scores, mask)]

    #
    #
    #  -------- predict -----------
    #
    def predict(
            self,
            batch: list,
    ) -> tuple:

        word_batch: list = []
        label_batch: list = []

        for row in batch:
            word_batch.append(row['text'])
            label_batch.append([row['label']])

        return self.forward(word_batch), label_batch

    #
    #
    #  -------- loss -----------
    #
    def loss(
            self,
            batch: list,
    ) -> nn.CrossEntropyLoss:

        predictions, target_ids = self.predict(batch)

        return nn.CrossEntropyLoss()(
            torch.cat(predictions),
            torch.LongTensor(flatten(target_ids)).to(get_device()),
        )

    #
    #
    #  -------- accuracy -----------
    #
    @torch.no_grad()
    def accuracy(
            self,
            batch: list,
            reset: bool = True,
            category: str = None,
    ) -> float:
        self.eval()

        if reset:
            self.metric.reset()

        predictions, target_ids = self.predict(batch)

        # Process the predictions and compare with the gold labels
        for pred, gold in zip(predictions, target_ids):
            for (p, g) in zip(pred, gold):

                p_idx: int = torch.argmax(p).item()

                if p_idx == g:
                    self.metric.add_tp(p_idx)

                    for c in self.metric.get_classes():
                        if c != p_idx:
                            self.metric.add_tn(p_idx)

                if p_idx != g:
                    self.metric.add_fp(p_idx)
                    self.metric.add_fn(g)

        return self.metric.f_score(class_name=category)

    #
    #
    #  -------- evaluate -----------
    #
    @torch.no_grad()
    def evaluate(
            self,
            data_loader,
            category: str = None,
    ) -> float:
        self.eval()
        self.metric.reset()

        for batch in data_loader:
            _ = self.accuracy(batch, reset=False)

        return self.metric.f_score(class_name=category)

    #  -------- save -----------
    #
    def save(self, path: str) -> None:

        torch.save(
            {
                "config": self.config,
                "state_dict": self.state_dict(),
                "metric": self.metric,
            },
            path + ".pickle",
        )

    #  -------- load -----------
    #
    @classmethod
    def load(cls, path: str) -> nn.Module:

        data = torch.load(path + ".pickle")

        model: nn.Module = cls(data["config"]).to(get_device())
        model.load_state_dict(data["state_dict"])

        return model

    #  -------- copy -----------
    #
    @classmethod
    def copy(cls, model: nn.Module) -> nn.Module:

        copy: nn.Module = cls(model.config).to(get_device())
        copy.load_state_dict(model.state_dict())

        return copy

    #  -------- __len__ -----------
    #
    def __len__(self) -> int:
        return sum(p.numel() for p in self.parameters())
