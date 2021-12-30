import torch
import torch.nn as nn

from challenge.nn import MLP, GRU
from challenge.util import flatten, get_device


class Model(nn.Module):

    #
    #
    #  -------- init -----------
    #
    def __init__(self, config: dict, embedding):
        super().__init__()

        if config is None:
            config = self._default_config()

        self.config = config
        self.embedding = embedding

        self.emb_dropout = nn.Dropout(p=self.embedding.dropout, inplace=False)

        # RNN to calculate contextualized word embedding
        self.context = GRU(
            in_size=self.embedding.dimension,
            hid_size=self.config["rnn"]["hid_size"],
            depth=self.config["rnn"]["depth"],
            dropout=self.config["rnn"]["dropout"],
        )

        # MLP to calculate the POS tags
        self.score = MLP(
            in_size=self.config["rnn"]["hid_size"] * 2,
            hid_size=self.config["score"]["hid_size"],
            out_size=2,
            dropout=self.config["score"]["dropout"],
        )

    #
    #
    #  -------- _default_config -----------
    #
    @staticmethod
    def _default_config() -> dict:
        return {
            "rnn": {
                "hid_size": 64,
                "depth": 2,
                "dropout": 0.2
            },
            "score": {
                "hid_size": 32,
                "dropout": 0.2
            }
        }

    #
    #
    #  -------- forward -----------
    #
    def forward(self, batch: list) -> list:

        # embed batch and apply dropout
        embed_batch: list = [self.emb_dropout(row) for row in self.embedding.forward_batch(batch)]

        # Contextualize embedding with BiLSTM
        pad_context, mask, hidden = self.context(embed_batch)

        # Calculate the score using the sum of all context prediction:
        # return [torch.sum(pred, dim=0, keepdim=True) for pred in unpad(self.score(pad_context), mask)]

        # Calculate the score using last hidden context state:
        return self.score(torch.cat((hidden[-2, :, :], hidden[-1, :, :]), dim=1))

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

            # append bert input: ['input_ids', 'attention_mask]
            if type(self.embedding).__name__ == "Bert":
                word_batch.append({'input_ids': row['input_ids'], 'attention_mask': row['attention_mask']})

            # append regular input: 'text tokens'
            else:
                word_batch.append(row['text'])

            label_batch.append([row['label']])

        return self.forward(word_batch), torch.LongTensor(flatten(label_batch)).to(get_device())

    #  -------- save -----------
    #
    def save(self, path: str) -> None:

        torch.save(
            {
                "config": self.config,
                "state_dict": self.state_dict()
            },
            path + ".pickle",
        )

    #  -------- load -----------
    #
    @classmethod
    def load(cls, path: str, embedding) -> nn.Module:

        data = torch.load(path + ".pickle")

        model: nn.Module = cls(data["config"], embedding).to(get_device())
        model.load_state_dict(data["state_dict"])

        return model

    #  -------- __len__ -----------
    #
    def __len__(self) -> int:
        return sum(p.numel() for p in self.parameters())