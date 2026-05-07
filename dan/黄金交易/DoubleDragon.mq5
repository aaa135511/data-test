//+------------------------------------------------------------------+
//|                                         DoubleDragon_Ultimate.mq5|
//|                                  核心任务：突破200点/3分钟止损/日损300 |
//+------------------------------------------------------------------+
#property copyright "Expert"
#property link      "https://m.jrjr.com/"
#property version   "1.02"
#property strict

#include <Trade\Trade.mqh>

//--- 输入参数
input double LotSize        = 0.2;       // 优化：默认0.2手
input int    DistancePoints = 200;       // 挂单距离 (200点=2.00美元)
input int    TakeProfitPts  = 30;        // 止盈点数 (30点=0.3美元)
input double PriceMin       = 4000.0;    // 交易区间底价
input double PriceMax       = 6000.0;    // 交易区间顶价
input double DailyMaxLoss   = 300.0;     // 核心任务4：日亏损限制 (美元)
input int    TimeLimitMin   = 3;         // 核心任务3：持仓时间限制 (分钟)
input int    MagicNumber    = 888888;    // EA识别码
input int    Slippage       = 10;        // 优化：滑点0.1美元=10点

//--- 全局变量
CTrade trade;
datetime DayStartTime;
double   InitialBalance;

//+------------------------------------------------------------------+
//| 初始化                                                            |
//+------------------------------------------------------------------+
int OnInit()
{
    trade.SetExpertMagicNumber(MagicNumber);
    trade.SetDeviationInPoints(Slippage);

    DayStartTime = iTime(_Symbol, PERIOD_D1, 0);
    InitialBalance = AccountInfoDouble(ACCOUNT_BALANCE);

    Print("--- EA 已启动 ---");
    Print("当前设置：手数=", LotSize, " 滑点=", Slippage, " 日损限制=", DailyMaxLoss);
    return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| 主循环                                                            |
//+------------------------------------------------------------------+
void OnTick()
{
    // 1. 核心任务4：日损熔断检查
    if(!CheckDailyLoss()) return;

    // 2. 价格区间检查
    double currentPrice = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    if(currentPrice < PriceMin || currentPrice > PriceMax)
    {
        // 如果价格超出区间，清理所有挂单，等待价格回归
        CancelAllOrders();
        return;
    }

    // 3. 核心任务3：持仓管理（3分钟止损 & 保本）
    HandlePositions();

    // 4. 核心任务1 & 2：挂单逻辑 (包含自动刷新逻辑，防止挂单跑远)
    ManageOrders();
}

//+------------------------------------------------------------------+
//| 核心任务4：日损 300 自动关机                                        |
//+------------------------------------------------------------------+
bool CheckDailyLoss()
{
    if(iTime(_Symbol, PERIOD_D1, 0) != DayStartTime)
    {
        DayStartTime = iTime(_Symbol, PERIOD_D1, 0);
        InitialBalance = AccountInfoDouble(ACCOUNT_BALANCE);
    }

    double currentEquity = AccountInfoDouble(ACCOUNT_EQUITY);
    double currentLoss = InitialBalance - currentEquity;

    if(currentLoss >= DailyMaxLoss)
    {
        Print("🔴 触发日损熔断！当前亏损: ", currentLoss, " 美元。执行自动关机。");
        CloseAllPositions();
        CancelAllOrders();
        ExpertRemove();
        return false;
    }
    return true;
}

//+------------------------------------------------------------------+
//| 核心任务3：时间止损 (3分钟)                                         |
//+------------------------------------------------------------------+
void HandlePositions()
{
    for(int i=PositionsTotal()-1; i>=0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if(PositionSelectByTicket(ticket))
        {
            if(PositionGetInteger(POSITION_MAGIC) == MagicNumber)
            {
                // 3分钟强制平仓
                long openTime = PositionGetInteger(POSITION_TIME);
                if(TimeCurrent() - openTime >= TimeLimitMin * 60)
                {
                    trade.PositionClose(ticket);
                    Print("⏰ [时间止损] 订单 #", ticket, " 持仓达3分钟，强制平仓。");
                    continue;
                }

                // 保本逻辑
                double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
                double curPrice = PositionGetDouble(POSITION_PRICE_CURRENT);
                double sl = PositionGetDouble(POSITION_SL);

                if(PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY)
                {
                    if(curPrice > openPrice + 40*_Point && sl < openPrice)
                        trade.PositionModify(ticket, openPrice + 2*_Point, 0);
                }
                else
                {
                    if(curPrice < openPrice - 40*_Point && (sl > openPrice || sl == 0))
                        trade.PositionModify(ticket, openPrice - 2*_Point, 0);
                }
            }
        }
    }
}

//+------------------------------------------------------------------+
//| 核心任务1 & 2：挂单逻辑 (优化：增加过期重挂)                         |
//+------------------------------------------------------------------+
void ManageOrders()
{
    int ordersCount = 0;
    int positionsCount = 0;
    double buyOrderPrice = 0;

    // 统计
    for(int i=PositionsTotal()-1; i>=0; i--)
        if(PositionSelectByTicket(PositionGetTicket(i)))
            if(PositionGetInteger(POSITION_MAGIC) == MagicNumber) positionsCount++;

    for(int i=OrdersTotal()-1; i>=0; i--)
    {
        if(OrderSelect(OrderGetTicket(i)))
        {
            if(OrderGetInteger(ORDER_MAGIC) == MagicNumber)
            {
                ordersCount++;
                if(OrderGetInteger(ORDER_TYPE) == ORDER_TYPE_BUY_STOP)
                    buyOrderPrice = OrderGetDouble(ORDER_PRICE_OPEN);
            }
        }
    }

    // 核心任务2：一单成交，删另一单 (OCO)
    if(positionsCount > 0)
    {
        if(ordersCount > 0)
        {
            CancelAllOrders();
            Print("✅ 核心任务2：检测到仓位已成交，撤销剩余挂单。");
        }
        return; // 有持仓时不挂新单
    }

    // --- 优化：挂单跟随逻辑 ---
    // 如果已有挂单，但现价距离挂单已经超过 400 点（跑远了），则撤销重挂，保证陷阱始终在现价附近
    double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    if(ordersCount > 0 && MathAbs(ask - buyOrderPrice) > (DistancePoints + 200) * _Point)
    {
        Print("🔄 价格已跑远，正在重置挂单位置...");
        CancelAllOrders();
        ordersCount = 0;
    }

    // 核心任务1：挂单
    if(positionsCount == 0 && ordersCount == 0)
    {
        double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
        double point = _Point;

        double buyStopPrice = ask + DistancePoints * point;
        double sellStopPrice = bid - DistancePoints * point;

        // 执行挂单
        trade.BuyStop(LotSize, buyStopPrice, _Symbol, 0, buyStopPrice + TakeProfitPts * point, ORDER_TIME_GTC, 0, "BuyTrack");
        trade.SellStop(LotSize, sellStopPrice, _Symbol, 0, sellStopPrice - TakeProfitPts * point, ORDER_TIME_GTC, 0, "SellTrack");

        Print("🚀 核心任务1：已在价格 ", buyStopPrice, " 和 ", sellStopPrice, " 设下陷阱。");
    }
}

//--- 清理函数
void CloseAllPositions()
{
    for(int i=PositionsTotal()-1; i>=0; i--)
        if(PositionSelectByTicket(PositionGetTicket(i)))
            if(PositionGetInteger(POSITION_MAGIC) == MagicNumber) trade.PositionClose(PositionGetTicket(i));
}

void CancelAllOrders()
{
    for(int i=OrdersTotal()-1; i>=0; i--)
        if(OrderSelect(OrderGetTicket(i)))
            if(OrderGetInteger(ORDER_MAGIC) == MagicNumber) trade.OrderDelete(OrderGetTicket(i));
}