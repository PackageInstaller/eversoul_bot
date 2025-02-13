from proto.HeroEquipRecommendation_pb2 import HeroEquipRecommendation

def inspect_binary_file(file_path):
    """检查二进制文件内容
    
    Args:
        file_path: 序列化文件的路径
    """
    with open(file_path, 'rb') as f:
        binary_data = f.read()
        print("文件大小:", len(binary_data), "字节")
        print("前20个字节的十六进制:", binary_data[:20].hex())

def analyze_and_read_hero_equip(file_path):
    """分析并读取HeroEquipRecommendation数据
    
    Args:
        file_path: 序列化文件的路径
    """
    from proto.HeroEquipRecommendation_pb2 import HeroEquipRecommendation
    
    with open(file_path, 'rb') as f:
        binary_data = f.read()
        
    print("完整十六进制内容:")
    print(binary_data.hex())
    
    # 尝试跳过前8个字节（可能是头部）
    try:
        data_without_header = binary_data[8:]
        hero_equip = HeroEquipRecommendation()
        hero_equip.ParseFromString(data_without_header)
        
        print("\n成功解析！数据内容：")
        for set_equip in hero_equip.heroSetEquipList:
            print(f"Set Effect Numbers: {list(set_equip.setEffectNo)}")
            print(f"Count: {set_equip.count}")
        return hero_equip
    except Exception as e:
        print(f"\n跳过8字节后解析失败: {str(e)}")
    
    # 如果上面失败，尝试其他偏移量
    for offset in [4, 12, 16]:
        try:
            data_without_header = binary_data[offset:]
            hero_equip = HeroEquipRecommendation()
            hero_equip.ParseFromString(data_without_header)
            print(f"\n成功！跳过{offset}字节后解析成功。数据内容：")
            for set_equip in hero_equip.heroSetEquipList:
                print(f"Set Effect Numbers: {list(set_equip.setEffectNo)}")
                print(f"Count: {set_equip.count}")
            return hero_equip
        except:
            print(f"\n尝试跳过{offset}字节失败")

def read_hero_equip_recommendation(file_path):
    """从序列化文件中读取HeroEquipRecommendation数据并格式化输出
    
    Args:
        file_path: 序列化文件的路径
    """
    from proto.HeroEquipRecommendation_pb2 import HeroEquipRecommendation
    
    with open(file_path, 'rb') as f:
        binary_data = f.read()
    
    # 跳过8字节的头部
    data_without_header = binary_data[8:]
    hero_equip = HeroEquipRecommendation()
    hero_equip.ParseFromString(data_without_header)
    
    print("\n装备组合推荐：")
    print("-" * 40)
    
    # 按数量排序
    sorted_equips = sorted(hero_equip.heroSetEquipList, 
                         key=lambda x: x.count, 
                         reverse=True)
    
    # 分类：双件套和单件套
    double_sets = []
    single_sets = []
    
    for set_equip in sorted_equips:
        if len(set_equip.setEffectNo) > 1:
            double_sets.append(set_equip)
        else:
            single_sets.append(set_equip)
    
    # 输出双件套信息
    if double_sets:
        print("\n双件套组合:")
        print("套装ID组合    使用次数")
        print("-" * 20)
        for set_equip in double_sets:
            print(f"{set_equip.setEffectNo} {set_equip.count:>8}次")
    
    # 输出单件套信息
    if single_sets:
        print("\n单件套使用:")
        print("套装ID    使用次数")
        print("-" * 20)
        for set_equip in single_sets:
            print(f"{set_equip.setEffectNo[0]:>3}    {set_equip.count:>8}次")

    return hero_equip

# 使用示例
file_path = "proto/HeroEquipRecommendation"  # 替换为你的文件路径
inspect_binary_file(file_path)  # 先检查文件内容
hero_equip = read_hero_equip_recommendation(file_path)