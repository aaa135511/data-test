import numpy as np


# 定义直觉模糊数类
class intuitionisticfuzzynumber:
    def __init__(self, mu, gamma):
        self.mu = mu  # 隶属度
        self.gamma = gamma  # 非隶属度
        # 确保数值合法性，允许微小浮点误差
        if not (0 <= self.mu <= 1 and 0 <= self.gamma <= 1 and 0 <= self.mu + self.gamma <= 1.000001):
            # 进行裁剪以确保合法性
            self.mu = max(0, min(self.mu, 1))
            self.gamma = max(0, min(self.gamma, 1))
            if self.mu + self.gamma > 1:
                # 按比例缩小 mu 和 gamma
                sum_val = self.mu + self.gamma
                self.mu /= sum_val
                self.gamma /= sum_val
        self.pi = 1 - self.mu - self.gamma  # 直觉指数（犹豫度）

    def __repr__(self):
        return f"<{self.mu:.4f}, {self.gamma:.4f}>"


# 直觉模糊Petri网类
class ifpn:
    def __init__(self, p, dt, di, didn, do, dodn, theta, th, dcdf):
        self.p = p
        self.dt = dt
        self.di = np.array(di)
        self.didn = np.array(didn)
        self.do = np.array(do)
        self.dodn = np.array(dodn)
        self.theta = theta
        self.th = th
        self.dcdf = dcdf

    # 加法算子⊕
    def add_operator(self, da, db):
        result = []
        for a, b in zip(da, db):
            mu = max(a.mu, b.mu)
            gamma = min(a.gamma, b.gamma)
            result.append(intuitionisticfuzzynumber(mu, gamma))
        return result

    # 乘法算子1⊗
    def multiply1_operator(self, da_mat, db_vec):
        da_mat = np.array(da_mat)
        rows, cols = da_mat.shape
        result = []
        for i in range(rows):
            mu_list = []
            gamma_list = []
            for j in range(cols):
                if da_mat[i, j] == 1:
                    mu_list.append(db_vec[j].mu)
                    gamma_list.append(db_vec[j].gamma)

            if not mu_list:  # 如果没有连接
                mu = 0
                gamma = 1
            else:
                mu = max(mu_list)
                gamma = min(gamma_list)
            result.append(intuitionisticfuzzynumber(mu, gamma))
        return result

    # 乘法算子2Ξ (使用更高效的Numpy广播)
    def multiply2_operator(self, da_mat, db_vec):
        da_mat = np.array(da_mat)
        db_mu_values = np.array([v.mu for v in db_vec])

        result_mu = np.max(da_mat * db_mu_values, axis=1)

        result = []
        for mu in result_mu:
            result.append(intuitionisticfuzzynumber(mu, 1 - mu))
        return result

    # 比较算子1⊙
    def compare1_operator(self, da, db):
        result = []
        for a, b in zip(da, db):
            if a.mu > b.mu and a.gamma < b.gamma:
                result.append(a)
            else:
                result.append(intuitionisticfuzzynumber(0, 1))
        return result

    # 比较算子2Θ
    def compare2_operator(self, da, db):
        result = []
        for a, b in zip(da, db):
            if a.mu >= b.mu and a.gamma <= b.gamma:
                result.append(a)
            else:
                result.append(intuitionisticfuzzynumber(0, 1))
        return result

    # 直乘算子∘
    def dot_multiply_operator(self, da_vec, db_vec):
        result = []
        for a, b in zip(da_vec, db_vec):
            mu = a.mu * b.mu
            gamma = a.gamma + b.gamma - a.gamma * b.gamma
            result.append(intuitionisticfuzzynumber(mu, gamma))
        return result

    # 向量否定算子neg
    def neg_operator(self, vec):
        result = []
        for v in vec:
            result.append(intuitionisticfuzzynumber(v.gamma, v.mu))
        return result

    # 信息熵计算
    def info_entropy(self, ifn):
        # 约定 0*log(0) = 0
        term1 = -ifn.mu * np.log2(ifn.mu) if ifn.mu > 0 else 0
        term2 = -ifn.gamma * np.log2(ifn.gamma) if ifn.gamma > 0 else 0
        pi = 1 - ifn.mu - ifn.gamma
        term3 = -pi * np.log2(pi) if pi > 0 else 0
        return term1 + term2 + term3

    # 调整直觉模糊数
    def adjust_ifn(self, ifn_list, alpha):
        if not ifn_list: return []
        entropies = [self.info_entropy(ifn) for ifn in ifn_list]
        avg_entropy = sum(entropies) / len(entropies)

        adjusted = []
        for ifn, e in zip(ifn_list, entropies):
            pi_prime = ifn.pi + alpha * (e - avg_entropy)
            pi_prime = max(0, min(pi_prime, 1))  # 确保犹豫度在[0,1]

            sum_mu_gamma = ifn.mu + ifn.gamma
            if sum_mu_gamma == 0:
                mu_prime, gamma_prime = (1 - pi_prime) / 2, (1 - pi_prime) / 2
            else:
                mu_prime = (ifn.mu / sum_mu_gamma) * (1 - pi_prime)
                gamma_prime = (ifn.gamma / sum_mu_gamma) * (1 - pi_prime)
            adjusted.append(intuitionisticfuzzynumber(mu_prime, gamma_prime))
        return adjusted

    # 判断是否收敛的辅助函数
    def is_converged(self, current, previous, eps=1e-6):
        if len(current) != len(previous): return False
        for c, p in zip(current, previous):
            if abs(c.mu - p.mu) > eps or abs(c.gamma - p.gamma) > eps:
                return False
        return True

    # 反向推理精简模型
    def backward_reasoning(self, dx0, dy0):
        dx_prev = [intuitionisticfuzzynumber(x, 1 - x) if not isinstance(x, intuitionisticfuzzynumber) else x for x in
                   dx0]
        dy_prev = [intuitionisticfuzzynumber(y, 1 - y) if not isinstance(y, intuitionisticfuzzynumber) else y for y in
                   dy0]

        print("\n--- 开始反向推理 ---")
        print(f"初始相关库所 X0 (μ): {[x.mu for x in dx_prev]}")

        max_iter = 10
        for k in range(1, max_iter + 1):
            print(f"\n迭代 {k}:")
            do_plus_dodn = self.do + self.dodn
            dy_k = self.multiply2_operator(do_plus_dodn, dx_prev)
            di_plus_didn = self.di + self.didn
            temp = self.multiply2_operator(di_plus_didn, dy_k)
            dx_k = self.add_operator(temp, dx_prev)
            print(f"Y_{k} (μ): {[f'{y.mu:.1f}' for y in dy_k]}")
            print(f"X_{k} (μ): {[f'{x.mu:.1f}' for x in dx_k]}")

            if self.is_converged(dx_k, dx_prev) and self.is_converged(dy_k, dy_prev):
                print(f"\n在第 {k} 次迭代后收敛。")
                break

            dx_prev, dy_prev = dx_k, dy_k
            if k == max_iter:
                print("\n警告：反向推理达到最大迭代次数。")

        print("\n--- 执行模型精简 ---")
        places_to_keep = [i for i, x in enumerate(dx_k) if x.mu > 0]
        transitions_to_keep = [i for i, y in enumerate(dy_k) if y.mu > 0]

        if not places_to_keep or not transitions_to_keep:
            raise ValueError("反向推理未能找到任何相关的库所或变迁，无法精简模型。")

        new_p = [self.p[i] for i in places_to_keep]
        new_dt = [self.dt[i] for i in transitions_to_keep]
        new_theta = [self.theta[i] for i in places_to_keep]
        new_th = [self.th[i] for i in transitions_to_keep]
        new_dcdf = [self.dcdf[i] for i in transitions_to_keep]

        new_di = self.di[np.ix_(places_to_keep, transitions_to_keep)]
        new_didn = self.didn[np.ix_(places_to_keep, transitions_to_keep)]
        new_do = self.do[np.ix_(transitions_to_keep, places_to_keep)]
        new_dodn = self.dodn[np.ix_(transitions_to_keep, places_to_keep)]

        print(f"模型精简完成。")
        print(f"保留的库所 ({len(new_p)}个): {new_p}")
        print(f"保留的变迁 ({len(new_dt)}个): {new_dt}")

        return ifpn(new_p, new_dt, new_di, new_didn, new_do, new_dodn, new_theta, new_th, new_dcdf)

    # 正向故障推理
    def forward_reasoning(self, alpha):
        print("\n--- 开始正向推理 (在精简模型上) ---")

        theta = self.adjust_ifn(self.theta, alpha)
        dth = self.adjust_ifn(self.th, alpha)
        dcdf = self.adjust_ifn(self.dcdf, alpha)

        # --- 新增: 打印初始调整后的参数 ---
        print("\n--- 初始调整后的参数 (α={}) ---".format(alpha))
        print("调整后的 theta (初始库所可信度):")
        for i, p_name in enumerate(self.p):
            print(f"  {p_name}: {theta[i]}")
        print("\n调整后的 dth (变迁触发阈值):")
        for i, t_name in enumerate(self.dt):
            print(f"  {t_name}: {dth[i]}")
        print("\n调整后的 dcdf (规则可信度):")
        for i, t_name in enumerate(self.dt):
            print(f"  {t_name}: {dcdf[i]}")
        # --- 结束新增 ---

        theta_prev = theta
        rho_k_prev = [intuitionisticfuzzynumber(0, 1) for _ in self.dt]

        max_iter = 100
        for k in range(1, max_iter + 1):
            print(f"\n{'=' * 15} 正向推理迭代 {k} {'=' * 15}")
            print("\n--- 迭代开始时各库所可信度 (theta_prev) ---")
            for i, p_name in enumerate(self.p):
                print(f"  {p_name}: {theta_prev[i]}")

            # --- 新增: 详细打印每一步的计算 ---
            neg_theta = self.neg_operator(theta_prev)
            part1 = self.multiply1_operator(self.di.T, neg_theta)
            part2 = self.multiply1_operator(self.didn.T, theta_prev)
            rho_k = self.neg_operator(self.add_operator(part1, part2))
            print("\n--- (22) 计算各变迁的等效输入 (rho_k) ---")
            for i, t_name in enumerate(self.dt):
                print(f"  {t_name}: {rho_k[i]}")

            rho_k_prime = self.compare1_operator(rho_k, rho_k_prev)
            print("\n--- (23) 抑制重复触发后 (rho_k_prime) ---")
            print("  (与上一轮触发的 rho_k_prev 比较，只有信度增强的才能通过)")
            for i, t_name in enumerate(self.dt):
                print(f"  {t_name}: {rho_k_prime[i]}")

            rho_k_double_prime = self.compare2_operator(rho_k_prime, dth)
            print("\n--- (24) 与变迁阈值 dth 比较后 (rho_k_double_prime) ---")
            print("  (只有 mu > 0 的变迁才会被实际触发)")
            for i, t_name in enumerate(self.dt):
                print(f"  {t_name}: {rho_k_double_prime[i]}")

            ds_k = self.dot_multiply_operator(dcdf, rho_k_double_prime)
            print("\n--- (25) 计算触发变迁的输出可信度 (S_k) ---")
            print("  (由 rho_k_double_prime 和 dcdf 直乘得到)")
            for i, t_name in enumerate(self.dt):
                print(f"  {t_name}: {ds_k[i]}")

            do_part = self.multiply1_operator(self.do.T, ds_k)
            dodn_part = self.multiply1_operator(self.dodn.T, self.neg_operator(ds_k))
            dy_k = self.add_operator(do_part, dodn_part)
            print("\n--- (26) 计算对各库所的可信度增量 (ΔY_k) ---")
            for i, p_name in enumerate(self.p):
                print(f"  {p_name}: {dy_k[i]}")
            # --- 结束新增 ---

            if all(x.mu == 0 for x in rho_k_double_prime):  # 使用 double_prime 判断实际触发
                print("\n没有变迁被实际触发，推理终止。")
                return theta_prev

            theta_k = self.add_operator(theta_prev, dy_k)
            print("\n--- (27) 更新后各库所的最终可信度 (theta_k) ---")
            for i, p_name in enumerate(self.p):
                print(f"  {p_name}: {theta_k[i]}")

            if self.is_converged(theta_k, theta_prev):
                print(f"\n在第 {k} 次正向迭代后收敛。")
                return theta_k

            theta_prev = theta_k
            rho_k_prev = rho_k  # 更新 rho_k_prev 为当前周期的 rho_k

            if k == max_iter:
                print("\n警告：正向推理达到最大迭代次数。")
                return theta_k

        return theta_prev


if __name__ == "__main__":
    print("--- 步骤1: 初始化完整Petri网模型 ---")
    p_names = [f'P{i}' for i in range(1, 15)]
    t_names = [f't{i}' for i in range(1, 6)]

    I = np.array([
        [1, 0, 0, 0, 0], [1, 0, 0, 0, 0], [0, 0, 0, 0, 1], [0, 1, 0, 0, 0], [0, 0, 0, 0, 1],
        [0, 0, 1, 0, 0], [0, 0, 1, 0, 0], [0, 0, 1, 0, 0], [0, 0, 1, 0, 0], [0, 0, 0, 0, 1],
        [0, 0, 0, 1, 0], [0, 0, 0, 0, 1], [0, 0, 0, 0, 1], [0, 0, 0, 0, 0]
    ])
    IN = np.zeros_like(I);
    IN[2, 1] = 1
    O = np.array([
        [0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1]
    ]);
    ON = np.zeros_like(O)

    theta0 = [
        intuitionisticfuzzynumber(0.1, 0.8), intuitionisticfuzzynumber(0.5, 0.3), intuitionisticfuzzynumber(0, 1),
        intuitionisticfuzzynumber(0.4, 0.3), intuitionisticfuzzynumber(0, 1), intuitionisticfuzzynumber(0.2, 0.7),
        intuitionisticfuzzynumber(0.8, 0.1), intuitionisticfuzzynumber(0.7, 0.1), intuitionisticfuzzynumber(0.3, 0.5),
        intuitionisticfuzzynumber(0, 1), intuitionisticfuzzynumber(0.6, 0.2), intuitionisticfuzzynumber(0, 1),
        intuitionisticfuzzynumber(0.4, 0.4), intuitionisticfuzzynumber(0, 1)
    ]
    th0 = [
        intuitionisticfuzzynumber(0.2, 0.6), intuitionisticfuzzynumber(0.3, 0.6), intuitionisticfuzzynumber(0.1, 0.7),
        intuitionisticfuzzynumber(0.2, 0.5), intuitionisticfuzzynumber(0.1, 0.8)
    ]
    cf0 = [
        intuitionisticfuzzynumber(0.7, 0.2), intuitionisticfuzzynumber(0.8, 0.1), intuitionisticfuzzynumber(0.6, 0.2),
        intuitionisticfuzzynumber(0.8, 0.1), intuitionisticfuzzynumber(0.7, 0.2)
    ]

    full_model = ifpn(p_names, t_names, I, IN, O, ON, theta0, th0, cf0)
    X0 = [0] * 13 + [1];
    Y0 = [0] * 5
    simplified_model = full_model.backward_reasoning(X0, Y0)
    alpha = 0.3
    final_theta = simplified_model.forward_reasoning(alpha)

    print("\n--- 最终故障诊断结果 ---")
    if final_theta:
        try:
            p14_new_name = 'P14'
            p14_new_index = simplified_model.p.index(p14_new_name)
            p14_credibility = final_theta[p14_new_index]
            print(f"对目标故障 '{p14_new_name}' 的最终可信度评估为: {p14_credibility}")
            print(f"  - 隶属度 (支持程度): {p14_credibility.mu:.4f}")
            print(f"  - 非隶属度 (反对程度): {p14_credibility.gamma:.4f}")
            print(f"  - 犹豫度 (不确定性): {p14_credibility.pi:.4f}")
        except ValueError:
            print("错误：目标故障P14不在精简后的模型中，这不符合预期。")