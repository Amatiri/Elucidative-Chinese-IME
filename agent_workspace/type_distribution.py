def ffpz(line):
    left = line.find("(")
    right = line.rfind(")")
    if line.strip() == "":
        return "已退出"
    if left == -1 or right == -1 or right < left:
        return "格式错误"
    prefix = line[:left]
    inside = line[left + 1:right]
    suffix = line[right + 1:]   
    items = inside.split()
    result = " ".join(prefix + item + suffix for item in items)
    return result
def main():
    print("通过括号将类型符分配给各通用符号的其余编码，r(oa oo oi)→roa roo roi")
    while True:
        line = input("输入：")
        result = ffpz(line)
        if result == "格式错误":
            print(result)
            continue
        elif result == "已退出":
            print(result)
            break
        print(result)
if __name__ == "__main__":
    main()
