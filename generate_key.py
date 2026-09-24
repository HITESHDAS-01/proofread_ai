"""Mint offline license keys: python generate_key.py [count]"""

from license import generate_license_key, is_valid_license_key


def main() -> None:
    import sys

    count = 1
    if len(sys.argv) > 1:
        try:
            count = max(1, int(sys.argv[1]))
        except ValueError:
            print("usage: python generate_key.py [count]")
            return
    for _ in range(count):
        key = generate_license_key()
        ok = is_valid_license_key(key)
        print(f"{key}  valid={ok}")


if __name__ == "__main__":
    main()
