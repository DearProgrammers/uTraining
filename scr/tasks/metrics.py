import math
import torch
import torch.nn.functional as F
from sklearn.metrics import f1_score, roc_auc_score, recall_score, precision_score, confusion_matrix
from functools import partial

def _student_t_map(mu, sigma, nu):
    sigma = F.softplus(sigma)
    nu = 2.0 + F.softplus(nu)
    return mu.squeeze(axis=-1), sigma.squeeze(axis=-1), nu.squeeze(axis=-1)

def student_t_loss(outs, y):
    mu, sigma, nu = outs[..., 0], outs[..., 1], outs[..., 2]
    mu, sigma, nu = _student_t_map(mu, sigma, nu)
    y = y.squeeze(axis=-1)

    nup1_half = (nu + 1.0) / 2.0
    part1 = 1.0 / nu * torch.square((y - mu) / sigma)
    Z = (
        torch.lgamma(nup1_half)
        - torch.lgamma(nu / 2.0)
        - 0.5 * torch.log(math.pi * nu)
        - torch.log(sigma)
    )

    ll = Z - nup1_half * torch.log1p(part1)
    return -ll.mean()

def gaussian_ll_loss(outs, y):
    mu, sigma = outs[..., 0], outs[..., 1]
    y = y.squeeze(axis=-1)
    sigma = F.softplus(sigma)
    ll = -1.0 * (
        torch.log(sigma)
        + 0.5 * math.log(2 * math.pi)
        + 0.5 * torch.square((y - mu) / sigma)
    )
    return -ll.mean()

def binary_cross_entropy(logits, y):
    # BCE loss requires squeezing last dimension of logits so it has the same shape as y
    # requires y to be float, since it's overloaded to represent a probability
    return F.binary_cross_entropy_with_logits(logits, y.float()) #.squeeze(-1)


def binary_accuracy(logits, y):
    return torch.eq(logits.squeeze(-1) >= 0, y).float().mean()


def cross_entropy(logits, y):
    logits = logits.view(-1, logits.shape[-1])
    y = y.view(-1)
    return F.cross_entropy(logits, y)


def soft_cross_entropy(logits, y, **kwargs):
    logits = logits.view(-1, logits.shape[-1])
    # target is now 2d (no target flattening)
    return F.cross_entropy(logits, y, **kwargs)


def accuracy(logits, y):
    logits = logits.view(-1, logits.shape[-1])
    if y.numel() > logits.shape[0]:
        # Mixup leads to this case: use argmax class
        y = y.argmax(dim=-1)
    y = y.view(-1)
    return torch.eq(torch.argmax(logits, dim=-1), y).float().mean()


def accuracy_at_k(logits, y, k=1):
    logits = logits.view(-1, logits.shape[-1])
    if y.numel() > logits.shape[0]:
        # Mixup leads to this case: use argmax class
        y = y.argmax(dim=-1)
    y = y.view(-1)
    return torch.topk(logits, k, dim=-1)[1].eq(y.unsqueeze(-1)).any(dim=-1).float().mean()


def f1_binary(logits, y):
    logits = logits.view(-1, logits.shape[-1])
    y = y.view(-1)
    y_hat = torch.argmax(logits, dim=-1)
    return f1_score(y.cpu().numpy(), y_hat.cpu().numpy(), average="binary")


def f1_macro(logits, y):
    logits = logits.view(-1, logits.shape[-1])
    y = y.view(-1)
    y_hat = torch.argmax(logits, dim=-1)
    return f1_score(y.cpu().numpy(), y_hat.cpu().numpy(), average="macro")


def f1_micro(logits, y):
    logits = logits.view(-1, logits.shape[-1])
    y = y.view(-1)
    y_hat = torch.argmax(logits, dim=-1)
    return f1_score(y.cpu().numpy(), y_hat.cpu().numpy(), average="micro")


def roc_auc_macro(logits, y):
    logits = logits.view(
        -1, logits.shape[-1]
    ).detach()  # KS: had to add detach to eval while training
    y = y.view(-1)
    return roc_auc_score(
        y.cpu().numpy(), F.softmax(logits, dim=-1).cpu().numpy()[:, 1], average="macro"
    )


def roc_auc_micro(logits, y):
    logits = logits.view(-1, logits.shape[-1])
    y = y.view(-1)
    return roc_auc_score(
        y.cpu().numpy(), F.softmax(logits, dim=-1).cpu().numpy()[:, 1], average="micro"
    )


def mse(outs, y, len_batch=None):
    # assert outs.shape[:-1] == y.shape and outs.shape[-1] == 1
    # outs = outs.squeeze(-1)
    if len(y.shape) < len(outs.shape):
        assert outs.shape[-1] == 1
        outs = outs.squeeze(-1)
    if len_batch is None:
        return F.mse_loss(outs, y)
    else:
        # Computes the loss of the first `lens` items in the batches
        # TODO document the use case of this
        mask = torch.zeros_like(outs, dtype=torch.bool)
        for i, l in enumerate(len_batch):
            mask[i, :l, :] = 1
        outs_masked = torch.masked_select(outs, mask)
        y_masked = torch.masked_select(y, mask)
        return F.mse_loss(outs_masked, y_masked)

def forecast_rmse(outs, y, len_batch=None):
    # TODO: generalize, currently for Monash dataset
    return torch.sqrt(F.mse_loss(outs, y, reduction='none').mean(1)).mean()

def mae(outs, y, len_batch=None):
    # assert outs.shape[:-1] == y.shape and outs.shape[-1] == 1
    # outs = outs.squeeze(-1)
    if len(y.shape) < len(outs.shape):
        assert outs.shape[-1] == 1
        outs = outs.squeeze(-1)
    if len_batch is None:
        return F.l1_loss(outs, y)
    else:
        # Computes the loss of the first `lens` items in the batches
        mask = torch.zeros_like(outs, dtype=torch.bool)
        for i, l in enumerate(len_batch):
            mask[i, :l, :] = 1
        outs_masked = torch.masked_select(outs, mask)
        y_masked = torch.masked_select(y, mask)
        return F.l1_loss(outs_masked, y_masked)


def recall_binary(logits, y):
    y_pred = (logits.squeeze(-1) >= 0).float()
    true_positives = (y_pred * y).sum()
    false_negatives = ((1 - y_pred) * y).sum()
    return true_positives / (true_positives + false_negatives)

def precision_binary(logits, y):
    y_pred = (logits.squeeze(-1) >= 0).float()
    true_positives = (y_pred * y).sum()
    false_positives = (y_pred * (1 - y)).sum()
    return true_positives / (true_positives + false_positives)

def specificity_binary(logits, y):
    y_pred = (logits.squeeze(-1) >= 0).float()
    true_negatives = ((1 - y_pred) * (1 - y)).sum()
    false_positives = (y_pred * (1 - y)).sum()
    return true_negatives / (true_negatives + false_positives)

# def recall_multilabel(logits, y):
#     y_pred = (logits.squeeze(-1) >= 0).float()
#     true_positives = (y_pred * y).sum(dim=0)
#     false_negatives = ((1 - y_pred) * y).sum(dim=0)
#     recall = true_positives / (true_positives + false_negatives)
#     recall[torch.isnan(recall)] = 0.0
#     return recall.mean()
#
# def precision_multilabel(logits, y):
#     y_pred = (logits.squeeze(-1) >= 0).float()
#     true_positives = (y_pred * y).sum(dim=0)
#     false_positives = (y_pred * (1 - y)).sum(dim=0)
#     precision = true_positives / (true_positives + false_positives)
#     precision[torch.isnan(precision)] = 0.0
#     return precision.mean()

def specificity_multilabel(logits, y):
    y_pred = (logits.squeeze(-1) >= 0).float()
    true_negatives = ((1 - y_pred) * (1 - y)).sum(dim=0)
    false_positives = (y_pred * (1 - y)).sum(dim=0)
    specificity = true_negatives / (true_negatives + false_positives)
    specificity[torch.isnan(specificity)] = 0.0
    return specificity.mean()

def recall_multilabel(logits, y):
    epsilon = 1e-7
    y_pred = (logits.squeeze(-1) >= 0).float()
    tp = torch.sum(y_pred * y,dim=0)
    fp = torch.sum(y_pred * (1 - y),dim=0)
    return torch.sum(tp) / (torch.sum(tp) + torch.sum(fp) + epsilon)

def precision_multilabel(logits, y):
    epsilon = 1e-7
    y_pred = (logits.squeeze(-1) >= 0).float()
    tp = torch.sum(y_pred * y, dim=0)
    fn = torch.sum((1 - y_pred) * y,dim=0)
    return torch.sum(tp) / (torch.sum(tp) + torch.sum(fn) + epsilon)



# Metrics that can depend on the loss
def loss(x, y, loss_fn):
    """ This metric may be useful because the training loss may add extra regularization (e.g. weight decay implemented as L2 penalty), while adding this as a metric skips the additional losses """
    return loss_fn(x, y)


def bpb(x, y, loss_fn):
    """ bits per byte (image density estimation, speech generation, char LM) """
    return loss_fn(x, y) / math.log(2)


def ppl(x, y, loss_fn):
    return torch.exp(loss_fn(x, y))


# should have a better way to do this
output_metric_fns = {
    "binary_cross_entropy": binary_cross_entropy,
    "cross_entropy": cross_entropy,
    "binary_accuracy": binary_accuracy,
    "accuracy": accuracy,
    'accuracy@3': partial(accuracy_at_k, k=3),
    'accuracy@5': partial(accuracy_at_k, k=5),
    'accuracy@10': partial(accuracy_at_k, k=10),
    "eval_loss": loss,
    "mse": mse,
    "mae": mae,
    "forecast_rmse": forecast_rmse,
    "f1_binary": f1_binary,
    "f1_macro": f1_macro,
    "f1_micro": f1_micro,
    "roc_auc_macro": roc_auc_macro,
    "roc_auc_micro": roc_auc_micro,
    "soft_cross_entropy": soft_cross_entropy,  # only for pytorch 1.10+
    "student_t": student_t_loss,
    "gaussian_ll": gaussian_ll_loss,
    "recall_binary": recall_binary,
    "precision_binary": precision_binary,
    "specificity_binary": specificity_binary,
    "recall_multilabel": recall_multilabel,
    "precision_multilabel": precision_multilabel,
    "specificity_multilabel": specificity_multilabel,
}

try:
    from segmentation_models_pytorch.utils.functional import iou
    from segmentation_models_pytorch.losses.focal import focal_loss_with_logits

    def iou_with_logits(pr, gt, eps=1e-7, threshold=None, ignore_channels=None):
        return iou(pr.sigmoid(), gt, eps=eps, threshold=threshold, ignore_channels=ignore_channels)

    output_metric_fns["iou"] = partial(iou, threshold=0.5)
    output_metric_fns["iou_with_logits"] = partial(iou_with_logits, threshold=0.5)
    output_metric_fns["focal_loss"] = focal_loss_with_logits
except ImportError:
    pass

loss_metric_fns = {
    "loss": loss,
    "bpb": bpb,
    "ppl": ppl,
}
metric_fns = {**output_metric_fns, **loss_metric_fns}  # TODO py3.9

