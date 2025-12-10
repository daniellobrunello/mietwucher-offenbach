"""Utility classes for building chains for processors"""
from functools import reduce
from typing import List

from flathunter.default_processors import AddressResolver
from flathunter.default_processors import AddressGeocode
from flathunter.default_processors import GetPageHTMLProcessor
from flathunter.default_processors import Filter
from flathunter.default_processors import LambdaProcessor
from flathunter.default_processors import CrawlExposeDetails
# from flathunter.idmaintainer import SaveAllExposesProcessor
from flathunter.idmaintainer_mongo import SaveAllExposesProcessor
from flathunter.abstract_processor import Processor

class ProcessorChainBuilder:
    """Builder pattern for building chains of processors"""
    processors: List[Processor]

    def __init__(self, config):
        self.processors = []
        self.config = config

    def resolve_addresses(self):
        """Add processor that resolves addresses from expose pages"""
        self.processors.append(AddressResolver(self.config))
        return self
    
    def geocode_addresses(self):
        """Add processor that geocode addresses"""
        self.processors.append(AddressGeocode(self.config))
        return self

    def calculate_durations(self):
        return self

    def crawl_expose_details(self):
        """Add processor to crawl expose details"""
        self.processors.append(CrawlExposeDetails(self.config))
        return self

    def map(self, func):
        """Add processor that applies a lambda to exposes"""
        self.processors.append(LambdaProcessor(self.config, func))
        return self

    def apply_filter(self, filter_set):
        """Add processor that applies a filter to expose sequence"""
        self.processors.append(Filter(self.config, filter_set))
        return self

    def get_page_html(self):
        self.processors.append(GetPageHTMLProcessor(self.config))
        return self

    def save_all_exposes(self, id_watch):
        """Add processor that saves all exposes to disk"""
        self.processors.append(SaveAllExposesProcessor(self.config, id_watch))
        return self

    def build(self):
        """Build the processor chain"""
        return ProcessorChain(self.processors)

class ProcessorChain:
    """Class to hold a chain of processors"""
    processors: List[Processor]

    def __init__(self, processors):
        self.processors = processors

    def process(self, exposes):
        """Process the sequences of exposes with the processor chain"""
        return reduce((lambda exposes, processor: processor.process_exposes(exposes)),
                      self.processors, exposes)

    @staticmethod
    def builder(config):
        """Return a new processor chain builder"""
        return ProcessorChainBuilder(config)
