import json
import os
import uuid
from contextlib import contextmanager
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import URLError
from urllib.request import Request, urlopen

import boto3
import pika
import psycopg
import pymysql
import redis
from botocore.exceptions import BotoCoreError, ClientError
from psycopg.rows import dict_row
from pymysql.cursors import DictCursor
from redis.exceptions import RedisError

SERVICE = os.getenv("SERVICE_NAME", "api")
PRODUCTS = [
    {"id": "sku-100", "name": "Everyday Backpack", "price": 39.99},
    {"id": "sku-200", "name": "Ceramic Mug", "price": 12.50},
]


@contextmanager
def mysql_connection():
    connection = pymysql.connect(
        host=os.getenv("MYSQL_HOST", "mysql"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "retail"),
        password=os.getenv("MYSQL_PASSWORD", "retail-demo"),
        database=os.getenv("MYSQL_DATABASE", "retail"),
        cursorclass=DictCursor,
        connect_timeout=3,
    )
    try:
        with connection:
            yield connection
    finally:
        connection.close()


@contextmanager
def postgres_connection():
    connection = psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER", "retail"),
        password=os.getenv("POSTGRES_PASSWORD", "retail-demo"),
        dbname=os.getenv("POSTGRES_DATABASE", "retail"),
        connect_timeout=3,
        row_factory=dict_row,
    )
    try:
        with connection:
            yield connection
    finally:
        connection.close()


@lru_cache(maxsize=1)
def dynamodb_table():
    dynamodb = boto3.resource(
        "dynamodb",
        region_name=os.getenv("AWS_REGION", "us-east-1"),
        endpoint_url=os.getenv("DYNAMODB_ENDPOINT", "http://dynamodb:8000"),
        aws_access_key_id="local",
        aws_secret_access_key="local",
    )
    table_name = os.getenv("DYNAMODB_TABLE", "retail-cart")
    try:
        table = dynamodb.Table(table_name)
        table.load()
    except dynamodb.meta.client.exceptions.ResourceNotFoundException:
        table = dynamodb.create_table(
            TableName=table_name,
            KeySchema=[
                {"AttributeName": "user_id", "KeyType": "HASH"},
                {"AttributeName": "product_id", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "product_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        table.wait_until_exists()
    return table


def normalize_items(items):
    if not isinstance(items, list) or not items:
        raise ValueError("items must be a non-empty list")
    normalized = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("each item must be an object")
        product_id = item.get("product_id")
        quantity = item.get("quantity")
        if not isinstance(product_id, str) or not product_id or len(product_id) > 128:
            raise ValueError("each item needs a valid product_id")
        if type(quantity) is not int or quantity < 1 or quantity > 100:
            raise ValueError("quantity must be an integer between 1 and 100")
        normalized.append({"product_id": product_id, "quantity": quantity})
    return normalized


def publish_order(order):
    credentials = pika.PlainCredentials(
        os.getenv("RABBITMQ_USERNAME", "retail"),
        os.getenv("RABBITMQ_PASSWORD", "retail-demo"),
    )
    parameters = pika.ConnectionParameters(
        host=os.getenv("RABBITMQ_HOST", "rabbitmq"),
        port=int(os.getenv("RABBITMQ_PORT", "5672")),
        credentials=credentials,
        socket_timeout=3,
        blocked_connection_timeout=3,
    )
    connection = pika.BlockingConnection(parameters)
    try:
        channel = connection.channel()
        queue = os.getenv("RABBITMQ_QUEUE", "orders")
        channel.queue_declare(queue=queue, durable=True)
        channel.confirm_delivery()
        channel.basic_publish(
            exchange="",
            routing_key=queue,
            body=json.dumps(order),
            mandatory=True,
            properties=pika.BasicProperties(
                content_type="application/json", delivery_mode=2
            ),
        )
    finally:
        connection.close()


def dependency_unavailable(handler, dependency, error):
    print(f"{SERVICE}: {dependency} unavailable: {error}", flush=True)
    handler.send_json(503, {"error": "dependency_unavailable", "dependency": dependency})


def check_dependencies(handler):
    try:
        if SERVICE == "catalog":
            with mysql_connection() as connection, connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        elif SERVICE == "cart":
            dynamodb_table().load()
        elif SERVICE == "checkout":
            cache = redis.Redis(
                host=os.getenv("REDIS_HOST", "redis"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                socket_connect_timeout=3,
            )
            try:
                cache.ping()
            finally:
                cache.close()
        elif SERVICE == "orders":
            with postgres_connection() as connection, connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            credentials = pika.PlainCredentials(
                os.getenv("RABBITMQ_USERNAME", "retail"),
                os.getenv("RABBITMQ_PASSWORD", "retail-demo"),
            )
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=os.getenv("RABBITMQ_HOST", "rabbitmq"),
                    port=int(os.getenv("RABBITMQ_PORT", "5672")),
                    credentials=credentials,
                    socket_timeout=3,
                )
            )
            connection.close()
        handler.send_json(200, {"status": "ready", "service": SERVICE})
    except pymysql.MySQLError as error:
        dependency_unavailable(handler, "mysql", error)
    except psycopg.Error as error:
        dependency_unavailable(handler, "postgres", error)
    except (BotoCoreError, ClientError) as error:
        dependency_unavailable(handler, "dynamodb", error)
    except RedisError as error:
        dependency_unavailable(handler, "redis", error)
    except pika.exceptions.AMQPError as error:
        dependency_unavailable(handler, "rabbitmq", error)
    except OSError as error:
        dependency_unavailable(handler, "rabbitmq", error)


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def read_json(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("invalid content length") from None
        if size < 1 or size > 1024 * 1024:
            raise ValueError("request body must be between 1 byte and 1 MiB")
        try:
            return json.loads(self.rfile.read(size))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError("invalid JSON") from error

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"status": "ok", "service": SERVICE})
        elif self.path == "/ready":
            check_dependencies(self)
        elif self.path == "/products" and SERVICE == "catalog":
            try:
                with mysql_connection() as connection, connection.cursor() as cursor:
                    cursor.execute(
                        "CREATE TABLE IF NOT EXISTS products ("
                        "id VARCHAR(128) PRIMARY KEY, name VARCHAR(255) NOT NULL, "
                        "price DECIMAL(10, 2) NOT NULL)"
                    )
                    cursor.executemany(
                        "INSERT IGNORE INTO products (id, name, price) VALUES (%s, %s, %s)",
                        [(p["id"], p["name"], p["price"]) for p in PRODUCTS],
                    )
                    cursor.execute("SELECT id, name, price FROM products ORDER BY id")
                    items = [
                        {**item, "price": float(item["price"])}
                        for item in cursor.fetchall()
                    ]
                self.send_json(200, {"items": items})
            except pymysql.MySQLError as error:
                dependency_unavailable(self, "mysql", error)
        elif self.path == "/cart" and SERVICE == "cart":
            user_id = self.headers.get("X-User-Id", "demo-user")
            if not user_id or len(user_id) > 128:
                self.send_json(400, {"error": "invalid_user_id"})
                return
            try:
                from boto3.dynamodb.conditions import Key

                response = dynamodb_table().query(
                    KeyConditionExpression=Key("user_id").eq(user_id)
                )
                items = [
                    {**item, "quantity": int(item["quantity"])}
                    for item in response.get("Items", [])
                ]
                self.send_json(
                    200,
                    {
                        "items": items,
                        "count": len(items),
                    },
                )
            except (BotoCoreError, ClientError) as error:
                dependency_unavailable(self, "dynamodb", error)
        elif self.path == "/orders" and SERVICE == "orders":
            try:
                with postgres_connection() as connection, connection.cursor() as cursor:
                    cursor.execute(
                        "CREATE TABLE IF NOT EXISTS orders ("
                        "id UUID PRIMARY KEY, request_key VARCHAR(255) UNIQUE NOT NULL, "
                        "items JSONB NOT NULL, status VARCHAR(32) NOT NULL, "
                        "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"
                    )
                    cursor.execute(
                        "SELECT id, items, status, created_at FROM orders "
                        "ORDER BY created_at DESC LIMIT 100"
                    )
                    orders = [
                        {**order, "id": str(order["id"]), "created_at": order["created_at"].isoformat()}
                        for order in cursor.fetchall()
                    ]
                self.send_json(200, {"items": orders})
            except psycopg.Error as error:
                dependency_unavailable(self, "postgres", error)
        else:
            self.send_json(404, {"error": "not_found"})

    def do_POST(self):
        if not (
            (self.path == "/cart" and SERVICE == "cart")
            or (self.path == "/orders" and SERVICE == "orders")
            or (self.path == "/checkout" and SERVICE == "checkout")
        ):
            self.send_json(404, {"error": "not_found"})
            return
        try:
            body = self.read_json()
        except ValueError as error:
            self.send_json(400, {"error": str(error)})
            return

        if self.path == "/cart" and SERVICE == "cart":
            try:
                item = normalize_items([body])[0]
            except ValueError as error:
                self.send_json(400, {"error": str(error)})
                return
            user_id = self.headers.get("X-User-Id", "demo-user")
            if not user_id or len(user_id) > 128:
                self.send_json(400, {"error": "invalid_user_id"})
                return
            try:
                dynamodb_table().update_item(
                    Key={"user_id": user_id, "product_id": item["product_id"]},
                    UpdateExpression="ADD quantity :quantity",
                    ExpressionAttributeValues={":quantity": item["quantity"]},
                )
                self.send_json(200, {"status": "added", **item})
            except (BotoCoreError, ClientError) as error:
                dependency_unavailable(self, "dynamodb", error)
        elif self.path == "/orders" and SERVICE == "orders":
            try:
                items = normalize_items(body.get("items") if isinstance(body, dict) else None)
            except ValueError as error:
                self.send_json(400, {"error": str(error)})
                return
            request_key = self.headers.get("Idempotency-Key") or str(uuid.uuid4())
            if len(request_key) > 255:
                self.send_json(400, {"error": "idempotency key is too long"})
                return
            order = None
            try:
                with postgres_connection() as connection, connection.cursor() as cursor:
                    cursor.execute(
                        "CREATE TABLE IF NOT EXISTS orders ("
                        "id UUID PRIMARY KEY, request_key VARCHAR(255) UNIQUE NOT NULL, "
                        "items JSONB NOT NULL, status VARCHAR(32) NOT NULL, "
                        "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"
                    )
                    cursor.execute(
                        "INSERT INTO orders (id, request_key, items, status) "
                        "VALUES (%s, %s, %s, %s) ON CONFLICT (request_key) DO NOTHING "
                        "RETURNING id, items, status",
                        (uuid.uuid4(), request_key, json.dumps(items), "accepted"),
                    )
                    order = cursor.fetchone()
                    if order is None:
                        cursor.execute(
                            "SELECT id, items, status FROM orders WHERE request_key = %s",
                            (request_key,),
                        )
                        order = cursor.fetchone()
                    order = {**order, "id": str(order["id"])}
                publish_order(order)
                self.send_json(201, order)
            except psycopg.Error as error:
                dependency_unavailable(self, "postgres", error)
            except pika.exceptions.AMQPError as error:
                dependency_unavailable(self, "rabbitmq", error)
            except OSError as error:
                dependency_unavailable(self, "rabbitmq", error)
        elif self.path == "/checkout" and SERVICE == "checkout":
            try:
                items = normalize_items(body.get("items") if isinstance(body, dict) else None)
            except ValueError as error:
                self.send_json(400, {"error": str(error)})
                return
            request_key = self.headers.get("Idempotency-Key") or str(uuid.uuid4())
            cache = redis.Redis(
                host=os.getenv("REDIS_HOST", "redis"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
            cache_key = f"checkout:{request_key}"
            try:
                cached = cache.get(cache_key)
                if cached:
                    self.send_json(200, json.loads(cached))
                    return
                request = Request(
                    os.getenv("ORDERS_URL", "http://orders:8000") + "/orders",
                    data=json.dumps({"items": items}).encode(),
                    headers={
                        "Content-Type": "application/json",
                        "Idempotency-Key": request_key,
                    },
                    method="POST",
                )
                with urlopen(request, timeout=5) as response:
                    result = json.loads(response.read())
                checkout = {"status": "accepted", "order": result}
                cache.set(cache_key, json.dumps(checkout), ex=86400)
                self.send_json(201, checkout)
            except RedisError as error:
                dependency_unavailable(self, "redis", error)
            except URLError as error:
                dependency_unavailable(self, "orders", error)
            except OSError as error:
                dependency_unavailable(self, "orders", error)
            finally:
                cache.close()
        else:
            self.send_json(404, {"error": "not_found"})

    def log_message(self, fmt, *args):
        print(fmt % args, flush=True)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
