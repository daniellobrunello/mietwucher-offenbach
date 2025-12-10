"""Abstract class defining the 'Processor' interface"""
from typing import Dict

class Processor:
    """Processor interface. Flathunter runs sequences of exposes through
       a set of processors that stack on each other"""

    def process_expose(self, expose: Dict) -> Dict:
        """Mutate the expose. Should be implemented in the subclass"""
        return expose

    def process_exposes(self, exposes):
        """Apply the processor to every expose in the sequence"""
        return map(self.process_expose, exposes)
