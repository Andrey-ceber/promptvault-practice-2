"""Запуск: python -m promptvault --port 8782 --db data/promptvault.db."""
import argparse
from .web import make_server


def main():
    parser = argparse.ArgumentParser(description='PromptVault: Python + SQLite, local default 127.0.0.1')
    parser.add_argument('--host', choices=['127.0.0.1', '0.0.0.0'], default='127.0.0.1', help='0.0.0.0 only for isolated Docker container')
    parser.add_argument('--port', type=int, default=8782)
    parser.add_argument('--db', default='data/promptvault.db')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('port must be 1..65535')
    server = make_server(args.db, args.host, args.port)
    print(f'PromptVault: http://127.0.0.1:{args.port} | SQLite: {args.db}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
