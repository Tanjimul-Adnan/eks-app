import json
import os
import sys
import threading
import unittest
from contextlib import ExitStack
from decimal import Decimal
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from unittest.mock import MagicMock, Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import api_service


class ApiServiceTests(unittest.TestCase):
    def request(self, service, method, path, body=None, headers=None, patches=None):
        server = ThreadingHTTPServer(("127.0.0.1", 0), api_service.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        request_headers = headers or {}
        data = None if body is None else json.dumps(body).encode()
        if data is not None:
            request_headers["Content-Type"] = "application/json"
        request = Request(
            f"http://127.0.0.1:{server.server_port}{path}",
            data=data,
            headers=request_headers,
            method=method,
        )
        try:
            with patch.object(api_service, "SERVICE", service):
                with self.enter_patches(patches or []):
                    with urlopen(request, timeout=3) as response:
                        return response.status, json.loads(response.read())
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def enter_patches(self, patches):
        stack = ExitStack()
        for target, attribute, value in patches:
            stack.enter_context(patch.object(target, attribute, value))
        return stack

    def test_normalize_items_rejects_invalid_quantities(self):
        self.assertEqual(
            api_service.normalize_items(
                [{"product_id": "sku-100", "quantity": 2}]
            ),
            [{"product_id": "sku-100", "quantity": 2}],
        )
        for quantity in (0, -1, True, "2"):
            with self.subTest(quantity=quantity):
                with self.assertRaises(ValueError):
                    api_service.normalize_items(
                        [{"product_id": "sku-100", "quantity": quantity}]
                    )

    def test_mysql_connection_closes_once(self):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.side_effect = lambda *_: connection.close()
        with patch.object(api_service.pymysql, "connect", return_value=connection):
            with api_service.mysql_connection() as yielded_connection:
                self.assertIs(yielded_connection, connection)
        connection.close.assert_called_once()

    def test_order_publish_uses_broker_confirmation(self):
        connection = Mock()
        channel = Mock()
        connection.channel.return_value = channel
        with patch.object(
            api_service.pika, "BlockingConnection", return_value=connection
        ):
            api_service.publish_order({"id": "order-1"})
        channel.confirm_delivery.assert_called_once()
        channel.basic_publish.assert_called_once()
        connection.close.assert_called_once()

    def test_cart_serializes_dynamodb_decimal_quantities(self):
        table = Mock()
        table.query.return_value = {
            "Items": [
                {"user_id": "demo-user", "product_id": "sku-100", "quantity": Decimal(2)}
            ]
        }
        status, result = self.request(
            "cart",
            "GET",
            "/cart",
            patches=[(api_service, "dynamodb_table", lambda: table)],
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["items"][0]["quantity"], 2)

    def test_checkout_reuses_cached_idempotent_result(self):
        cache_data = {}
        cache = Mock()
        cache.get.side_effect = lambda key: cache_data.get(key)
        cache.set.side_effect = lambda key, value, ex: cache_data.__setitem__(key, value)
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'{"id":"order-1","status":"accepted"}'
        order_request = Mock(return_value=response)
        patches = [
            (api_service.redis, "Redis", Mock(return_value=cache)),
            (api_service, "urlopen", order_request),
        ]
        headers = {"Idempotency-Key": "checkout-1"}
        body = {"items": [{"product_id": "sku-100", "quantity": 1}]}

        first_status, first = self.request(
            "checkout", "POST", "/checkout", body, headers.copy(), patches
        )
        second_status, second = self.request(
            "checkout", "POST", "/checkout", body, headers.copy(), patches
        )

        self.assertEqual(first_status, 201)
        self.assertEqual(second_status, 200)
        self.assertEqual(second, first)
        order_request.assert_called_once()


if __name__ == "__main__":
    unittest.main()
