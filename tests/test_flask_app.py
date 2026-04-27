"""
Flask 应用测试 - 测试 webhook 端点（不实际启动服务器）
"""
import sys
import os
import json

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# 设置测试环境变量
os.environ['SUPABASE_URL'] = 'https://test.supabase.co'
os.environ['SUPABASE_KEY'] = 'test_key'
os.environ['FEISHU_APP_ID'] = 'cli_test123'
os.environ['FEISHU_APP_SECRET'] = 'test_secret'
os.environ['FEISHU_VERIFICATION_TOKEN'] = 'test_token'

from bot.main import app


def test_health_check():
    """测试健康检查端点"""
    print("=== 测试健康检查端点 ===")

    with app.test_client() as client:
        response = client.get('/health')

        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'healthy'
        assert 'service' in data
        assert 'version' in data

        print(f"✅ 健康检查通过")
        print(f"   响应: {data}")


def test_webhook_url_verification():
    """测试 URL 验证事件"""
    print("\n=== 测试 URL 验证事件 ===")

    with app.test_client() as client:
        # 模拟飞书 URL 验证请求
        payload = {
            'type': 'url_verification',
            'challenge': 'test_challenge_12345',
            'token': 'test_token'
        }

        response = client.post(
            '/webhook',
            data=json.dumps(payload),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data['challenge'] == 'test_challenge_12345'

        print(f"✅ URL 验证通过")
        print(f"   Challenge: {data['challenge']}")


def test_webhook_invalid_token():
    """测试无效 Token"""
    print("\n=== 测试无效 Token ===")

    with app.test_client() as client:
        payload = {
            'type': 'url_verification',
            'challenge': 'test_challenge',
            'token': 'wrong_token'
        }

        response = client.post(
            '/webhook',
            data=json.dumps(payload),
            content_type='application/json'
        )

        assert response.status_code == 403
        data = response.get_json()
        assert 'error' in data

        print(f"✅ 无效 Token 被正确拒绝")


def test_webhook_empty_body():
    """测试空请求体"""
    print("\n=== 测试空请求体 ===")

    with app.test_client() as client:
        response = client.post(
            '/webhook',
            data='',
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

        print(f"✅ 空请求体被正确拒绝")


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("Flask 应用测试")
    print("=" * 60 + "\n")

    tests = [
        ("健康检查", test_health_check),
        ("URL 验证", test_webhook_url_verification),
        ("无效 Token", test_webhook_invalid_token),
        ("空请求体", test_webhook_empty_body),
    ]

    results = []
    for name, test_func in tests:
        try:
            test_func()
            results.append((name, True))
        except AssertionError as e:
            print(f"❌ {name} 测试失败: {e}")
            results.append((name, False))
        except Exception as e:
            print(f"❌ {name} 测试出错: {e}")
            results.append((name, False))

    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")

    all_passed = all(r for _, r in results)

    if all_passed:
        print("\n🎉 所有测试通过!")
        return 0
    else:
        print("\n❌ 部分测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
