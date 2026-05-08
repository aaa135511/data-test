//+------------------------------------------------------------------+
//|                                         DoubleDragon_Pro_V3.mq5  |
//|                                  核心：突破200/OCO/3分钟/追踪止盈/日损300 |
//+------------------------------------------------------------------+
#property copyright "Expert"
#property link      "https://m.jrjr.com/"
#property version   "3.00"
#property strict

#include <Trade\Trade.mqh>

//--- 基础参数
input double LotSize         = 0.2;       // 交易手数
input int    Slippage        = 10;        // 滑点 (10点 = 0.1美元)
input int    MagicNumber     = 888888;    // EA识别码
input double DailyMaxLoss    = 300.0;     // 核心任务4：日亏损关机 (美元)

//--- 交易区间与时间
input double PriceMin        = 4000.0;    // 交易区间底价
input double PriceMax        = 6000.0;    // 交易区间顶价
input int    StartHourBJ     = 14;        // 北京时间开始 (下午14点)
input int    EndHourBJ       = 6;         // 北京时间结束 (次日凌晨6点)
input int    GMTOffset       = 5;         // 服务器时间比北京时间慢几个小时 (通常选5或6)

//--- 进场参数
input int    DistancePoints  = 200;       // 挂单距离 (200点 = 2.0美元)

//--- 移动止损/追踪止盈参数 (关键优化)
input int    InitialStopLoss = 500;       // 初始最大止损 (500点 = 5美元)
input int    TrailingStart   = 300;       // 获利多少点激活追踪 (300点 = 3美元)
input int    TrailingStop    = 100;       // 追踪回撤距离 (100点 = 1美元)
input int    TimeLimitMin    = 3;         // 核心任务3：持仓时间限制 (分钟)

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

    Print("--- EA Pro V3 已启动 ---");
    return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| 主循环                                                            |
//+------------------------------------------------------------------+
void OnTick()
{
    // 1. 核心任务4：日损检查
    if(!CheckDailyLoss()) return;

    // 2. 时间过滤：检查是否在欧美盘活跃时段
    if(!IsTradeTime())
    {
        // 不在交易时间，如果有挂单就撤销，但保留已有持仓（等待止损止盈）
        CancelAllOrders();
        return;
    }

    // 3. 价格区间检查
    double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    if(bid < PriceMin || bid > PriceMax) return;

    // 4. 核心任务3 & 动态管理：时间止损 + 移动止损/追踪止盈
    HandlePositionsAndTrailing();

    // 5. 核心任务1 & 2：突破挂单逻辑 (OCO)
    ManageOrders();
}

//+------------------------------------------------------------------+
//| 时间逻辑：北京时间转服务器时间                                      |
//+------------------------------------------------------------------+
bool IsTradeTime()
{
    MqlDateTime dt;
    TimeCurrent(dt);

    // 将当前服务器小时转换为北京时间进行判断
    int currentBJHour = (dt.hour + GMTOffset) % 24;

    if(StartHourBJ > EndHourBJ) // 跨天情况 (14点到次日6点)
    {
        if(currentBJHour >= StartHourBJ || currentBJHour < EndHourBJ) return true;
    }
    else // 不跨天
    {
        if(currentBJHour >= StartHourBJ && currentBJHour < EndHourBJ) return true;
    }
    return false;
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
    double currentLoss = InitialBalance - AccountInfoDouble(ACCOUNT_EQUITY);
    if(currentLoss >= DailyMaxLoss)
    {
        Print("🛑 触发日损限制！当前亏: ", currentLoss, "。EA自动下架。");
        CloseAllPositions();
        CancelAllOrders();
        ExpertRemove();
        return false;
    }
    return true;
}

//+------------------------------------------------------------------+
//| 核心优化：时间止损 + 追踪止盈止损                                   |
//+------------------------------------------------------------------+
void HandlePositionsAndTrailing()
{
    double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    double point = _Point;

    for(int i=PositionsTotal()-1; i>=0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if(PositionSelectByTicket(ticket))
        {
            if(PositionGetInteger(POSITION_MAGIC) == MagicNumber)
            {
                // --- A. 核心任务3：3分钟强制时间平仓 ---
                long openTime = PositionGetInteger(POSITION_TIME);
                if(TimeCurrent() - openTime >= TimeLimitMin * 60)
                {
                    trade.PositionClose(ticket);
                    Print("⏰ [时间止损] 订单 #", ticket, " 持仓达3分钟，强制离场。");
                    continue;
                }

                // --- B. 追踪止盈/止损逻辑 ---
                double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
                double currentSL = PositionGetDouble(POSITION_SL);
                long posType = PositionGetInteger(POSITION_TYPE);

                if(posType == POSITION_TYPE_BUY)
                {
                    double profitPoints = (bid - openPrice) / point;
                    // 如果获利超过追踪起点
                    if(profitPoints >= TrailingStart)
                    {
                        double newSL = bid - TrailingStop * point;
                        if(newSL > currentSL + 10 * point || currentSL == 0) // 只有往好方向移才更新
                        {
                            trade.PositionModify(ticket, NormalizeDouble(newSL, _Digits), 0);
                        }
                    }
                    // 初始最大止损保护 (如果还没设止损)
                    else if(currentSL == 0)
                    {
                        trade.PositionModify(ticket, NormalizeDouble(openPrice - InitialStopLoss * point, _Digits), 0);
                    }
                }
                else if(posType == POSITION_TYPE_SELL)
                {
                    double profitPoints = (openPrice - ask) / point;
                    if(profitPoints >= TrailingStart)
                    {
                        double newSL = ask + TrailingStop * point;
                        if(newSL < currentSL - 10 * point || currentSL == 0)
                        {
                            trade.PositionModify(ticket, NormalizeDouble(newSL, _Digits), 0);
                        }
                    }
                    else if(currentSL == 0)
                    {
                        trade.PositionModify(ticket, NormalizeDouble(openPrice + InitialStopLoss * point, _Digits), 0);
                    }
                }
            }
        }
    }
}

//+------------------------------------------------------------------+
//| 核心任务1 & 2：OCO 突破挂单管理                                    |
//+------------------------------------------------------------------+
void ManageOrders()
{
    int ordersCount = 0;
    int positionsCount = 0;

    for(int i=PositionsTotal()-1; i>=0; i--)
        if(PositionSelectByTicket(PositionGetTicket(i)))
            if(PositionGetInteger(POSITION_MAGIC) == MagicNumber) positionsCount++;

    for(int i=OrdersTotal()-1; i>=0; i--)
        if(OrderSelect(OrderGetTicket(i)))
            if(OrderGetInteger(ORDER_MAGIC) == MagicNumber) ordersCount++;

    // 核心任务2：一单成交，删另一单
    if(positionsCount > 0)
    {
        if(ordersCount > 0) CancelAllOrders();
        return;
    }

    // 核心任务1：无仓无单时，在上下200点挂单
    if(positionsCount == 0 && ordersCount == 0)
    {
        double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
        double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);

        double buyStopPrice = ask + DistancePoints * _Point;
        double sellStopPrice = bid - DistancePoints * _Point;

        // 挂单不设固定止盈，靠追踪逻辑离场
        trade.BuyStop(LotSize, buyStopPrice, _Symbol, buyStopPrice - InitialStopLoss * _Point, 0, ORDER_TIME_GTC, 0, "Pro_Buy");
        trade.SellStop(LotSize, sellStopPrice, _Symbol, sellStopPrice + InitialStopLoss * _Point, 0, ORDER_TIME_GTC, 0, "Pro_Sell");

        Print("🚀 突破单已挂出。等待激活...");
    }
}

//--- 工具函数
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