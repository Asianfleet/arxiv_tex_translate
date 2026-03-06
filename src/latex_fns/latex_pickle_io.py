import pickle


class SafeUnpickler(pickle.Unpickler):
    """
    安全的pickle反序列化类，只允许反序列化白名单中的类。

    用于防止pickle反序列化漏洞，只允许加载预先定义的类（如LatexPaperFileGroup、
    LatexPaperSplit、LinkedListNode等）。
    """

    def get_safe_classes(self):
        """
        获取允许反序列化的安全类列表。

        Returns:
            安全类名字典，键为类名，值为类对象
        """
        from latex_fns.latex_actions import LatexPaperFileGroup, LatexPaperSplit
        from latex_fns.latex_toolbox import LinkedListNode
        from numpy.core.multiarray import scalar
        from numpy import dtype
        # 定义允许的安全类
        safe_classes = {
            # 在这里添加其他安全的类
            'LatexPaperFileGroup': LatexPaperFileGroup,
            'LatexPaperSplit': LatexPaperSplit,
            'LinkedListNode': LinkedListNode,
            'scalar': scalar,
            'dtype': dtype,
        }
        return safe_classes

    def find_class(self, module, name):
        """
        重写find_class方法，只允许反序列化安全列表中的类。

        Args:
            module: 模块名
            name: 类名

        Returns:
            类对象

        Raises:
            pickle.UnpicklingError: 如果尝试加载未授权的类
        """
        # 只允许特定的类进行反序列化
        self.safe_classes = self.get_safe_classes()
        match_class_name = None
        for class_name in self.safe_classes.keys():
            if (class_name in f'{module}.{name}'):
                match_class_name = class_name
        if match_class_name is not None:
            return self.safe_classes[match_class_name]
        # 如果尝试加载未授权的类，则抛出异常
        raise pickle.UnpicklingError(f"Attempted to deserialize unauthorized class '{name}' from module '{module}'")

def objdump(obj, file="objdump.tmp"):
    """
    将对象序列化保存到文件。

    Args:
        obj: 要保存的Python对象
        file: 文件路径，默认为"objdump.tmp"
    """
    with open(file, "wb+") as f:
        pickle.dump(obj, f)
    return


def objload(file="objdump.tmp"):
    """
    从文件加载pickle对象（使用安全的反序列化器）。

    Args:
        file: 文件路径，默认为"objdump.tmp"

    Returns:
        加载的Python对象，如果文件不存在则返回None
    """
    import os

    if not os.path.exists(file):
        return
    with open(file, "rb") as f:
        unpickler = SafeUnpickler(f)
        return unpickler.load()
