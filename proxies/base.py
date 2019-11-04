from ..base import BaseServer, Response
from ..clients import BaseClient
from ..models import BaseModel
from ..cli import format_pyobj
from aiohttp import web
import itertools


class BaseProxy(BaseClient, BaseModel, BaseServer):
    requires = BaseClient, BaseModel, BaseServer
    search_path = '/search'
    train_path = '/train'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.queries = dict()
        self.counter = itertools.count()
        self.add_route('*', self.search_path)(self._search)
        self.add_route('*', self.train_path)(self._train)

    @BaseServer.add_state
    def queries(self):
        return self.queries

    @BaseServer.add_state
    def search_path(self):
        return self.search_path

    @BaseServer.add_state
    def train_path(self):
        return self.train_path

    async def _train(self, request: web.BaseRequest) -> web.Response:
        qid = int(request.headers['qid'])
        cid = int(request.headers['cid'])

        query, candidates = self.queries[qid]
        labels = [0] * len(candidates)
        labels[cid] = 1

        self.logger.info('TRAIN: %s' % query)
        self.logger.debug('candidates: %s\nlabels:%s' % (
            format_pyobj(candidates), format_pyobj(labels)))

        await self.train(query, candidates, labels)
        return Response.NO_CONTENT()

    async def _search(self, request: web.BaseRequest) -> web.Response:
        topk, method, ext_url, data = await self.magnify(request)
        async with self.client_handler(method, ext_url, data) as client_response:
            self.logger.info('RECV: ' + repr(client_response).split('\n')[0])

            query, candidates = await self.parse(request, client_response)
            self.logger.info('RANK: %s' % query)
            self.logger.debug('candidates: %s' % format_pyobj(candidates))
            ranks = await self.rank(query, candidates)
            reranked = [candidates[i] for i in ranks[:topk]]
            response = await self.format(client_response, reranked)
            qid = next(self.counter)
            self.queries[qid] = query, candidates
            response.headers['qid'] = str(qid)
            return response
