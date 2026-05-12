//+------------------------------------------------------------------+
//|                                         DoubleDragon_24H_V4.mq5 |
//|                                  核心：突破200/OCO/3分钟/24H极速追踪 |
//+------------------------------------------------------------------+
#property copyright "Expert"
#property link      "https://m.jrjr.com/"
#property version   "4.00"
#property strict

#include <Trade\Trade.mqh>

//--- 基础参数
input double LotSize         = 0.1;       // 优化：交易手数 0.1
input int    Slippage        = 10;        // 滑点 (10点 = 0.1美元)
input int    MagicNumber     = 888888;    // EA识别码
input double DailyMaxLoss    = 300.0;     // 核心任务4：日亏损关机 (美元)

//--- 交易价格区间
input double PriceMin        = 4000.0;    // 交易区间底价
input double PriceMax        = 6000.0;    // 交易区间顶价

//--- 进场参数
input int    DistancePoints  = 200;       // 核心任务1：挂单距离 (200点 = 2.0美元)

//--- 追踪与止损参数 (根据您的要求优化)
input int    InitialStopLoss = 10;        // 优化：初始止损 (10点 = 0.1美元)
input int    TrailingStart   = 5;         // 优化：获利多少点激活 (5点 = 0.05美元)
input int    TrailingStop    = 2;         // 优化：追踪回撤距离 (2点 = 0.02美元)
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

    Print("--- EA 24H 极速版 V4 已启动 ---");
    Print("设置：手数 0.1, 止损 10, 追踪开始 5, 追踪距离 2");
    return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| 主循环 (24小时不间断)                                               |
//+------------------------------------------------------------------+
void OnTick()
{
    // 1. 核心任务4：日损检查 (300美金熔断)
    if(!CheckDailyLoss()) return;

    // 2. 价格区间检查
    double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    if(bid < PriceMin || bid > PriceMax) return;

    // 3. 核心任务3 & 追踪管理：3分钟时间止损 + 极速追踪
    HandlePositionsAndTrailing();

    // 4. 核心任务1 & 2：挂单逻辑 (OCO 一单成交删另一单)
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
    double currentLoss = InitialBalance - AccountInfoDouble(ACCOUNT_EQUITY);
    if(currentLoss >= DailyMaxLoss)
    {
        Print("🛑 触发日损限制！当前亏损: ", currentLoss, " 美元。EA 自动关机。");
        CloseAllPositions();
        CancelAllOrders();
        ExpertRemove();
        return false;
    }
    return true;
}

//+------------------------------------------------------------------+
//| 极速管理：时间止损 + 5点激活2点追踪                                 |
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
                // --- 核心任务3：3分钟强制强制平仓 ---
                long openTime = PositionGetInteger(POSITION_TIME);
                if(TimeCurrent() - openTime >= TimeLimitMin * 60)
                {
                    trade.PositionClose(ticket);
                    Print("⏰ [时间止损] 订单 #", ticket, " 达到3分钟，强制离场。");
                    continue;
                }

                // --- 极速追踪逻辑 ---
                double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
                double currentSL = PositionGetDouble(POSITION_SL);
                long posType = PositionGetInteger(POSITION_TYPE);

                if(posType == POSITION_TYPE_BUY)
                {
                    double profitPoints = (bid - openPrice) / point;
                    if(profitPoints >= TrailingStart)
                    {
                        double newSL = bid - TrailingStop * point;
                        // 只有新止损价高于旧止损价才修改 (即不断提高保底线)
                        if(newSL > currentSL + point || currentSL == 0)
                        {
                            trade.PositionModify(ticket, NormalizeDouble(newSL, _Digits), 0);
                        }
                    }
                }
                else if(posType == POSITION_TYPE_SELL)
                {
                    double profitPoints = (openPrice - ask) / point;
                    if(profitPoints >= TrailingStart)
                    {
                        double newSL = ask + TrailingStop * point;
                        // 只有新止损价低于旧止损价才修改
                        if(newSL < currentSL - point || currentSL == 0)
                        {
                            trade.PositionModify(ticket, NormalizeDouble(newSL, _Digits), 0);
                        }
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

    // 统计当前 EA 的持仓和挂单
    for(int i=PositionsTotal()-1; i>=0; i--)
        if(PositionSelectByTicket(PositionGetTicket(i)))
            if(PositionGetInteger(POSITION_MAGIC) == MagicNumber) positionsCount++;

    for(int i=OrdersTotal()-1; i>=0; i--)
        if(OrderSelect(OrderGetTicket(i)))
            if(OrderGetInteger(ORDER_MAGIC) == MagicNumber) ordersCount++;

    // 核心任务2：一单成交，删另一单
    if(positionsCount > 0)
    {
        if(ordersCount > 0)
        {
            CancelAllOrders();
            Print("✅ 订单成交，已清理剩余挂单。");
        }
        return;
    }

    // 核心任务1：无持仓无挂单时，在上下 200 点挂单
    if(positionsCount == 0 && ordersCount == 0)
    {
        double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
        double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);

        double buyStopPrice = ask + DistancePoints * _Point;
        double sellStopPrice = bid - DistancePoints * _Point;

        // 挂单带初始 10 点止损
        trade.BuyStop(LotSize, buyStopPrice, _Symbol, buyStopPrice - InitialStopLoss * _Point, 0, ORDER_TIME_GTC, 0, "24H_Buy");
        trade.SellStop(LotSize, sellStopPrice, _Symbol, sellStopPrice + InitialStopLoss * _Point, 0, ORDER_TIME_GTC, 0, "24H_Sell");

        Print("🚀 24H 监听中：已在现价上下 200 点挂单。止损：10点。");
    }
}

//--- 工具函数：清理
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