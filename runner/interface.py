from abc import ABC, abstractmethod

class BrowserRunner(ABC):

    @abstractmethod
    def run(self, testcase_path: str):
        pass
